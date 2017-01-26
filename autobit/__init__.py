import json
from pprint import pformat
from functools import lru_cache
from operator import itemgetter

import attr
import requests
from unidecode import unidecode
from slimit.parser import Parser
from lxml.html import fromstring


pprint = lambda obj: print(unidecode(pformat(obj)))


def _load(val):
    if hasattr(val, 'items'):
        return [_load(t) for t in val.items]

    try:
        return json.loads(val.value)
    except (ValueError, TypeError, AttributeError):
        return eval(val.to_ecma())


class BittorrentError(Exception):
    pass


@attr.s
class Client:
    base_url = attr.ib()
    session = attr.ib(default=None)
    auth = attr.ib(default=None)

    def __attrs_post_init__(self):
        self.session = self.session or requests.Session()
        if self.auth:
            self.session.auth = self.auth

        if not self.base_url.endswith('/gui/'):
            self.base_url += '/gui/'

    def refresh_token(self):
        if 'token' in self.session.params:
            return

        r = self.session.get(self.base_url + 'token.html')
        self.session.params['token'] = (
            fromstring(r.text)
            .xpath('.//div/text()')[0]
        )

    def get(self, params):
        self.refresh_token()
        r = self.session.get(self.base_url, params=params).json()
        r.pop('build')
        return r

    def _get_msgs(self, key, keys):
        return [
            dict(zip(keys, rf))
            for rf in self.get({'list': 1, 'getmsg': 1})[key]
        ]

    @lru_cache()
    def consts(self):
        js = self.session.get(self.base_url + 'constants.js')

        root = Parser().parse(js.text)

        constants = root.children()[0].children()[0].initializer.properties
        return {
            assign.left.value: _load(assign.right)
            for assign in constants
        }

    @lru_cache()
    def keys(self, prefix):
        constants = self.consts()

        constants = {
            key: value
            for key, value in constants.items()
            if key.startswith(prefix)
        }

        return tuple(
            key[len(prefix):].lower()
            for key, _ in sorted(constants.items(), key=itemgetter(1))
        )

    def rss_update(self, params):
        res = self.get(
            dict(params, action='rss-update')
        )

        if 'rss_ident' in res:
            return int(res.get('rss_ident'))
        else:
            raise BittorrentError(res)

    def rss_remove(self, feed_id):
        return self.get({'action': 'rss-remove', 'feed-id': feed_id})

    def filter_update(self, params):
        res = self.get(
            dict(params, action='filter-update')
        )

        if 'filter-ident' in res:
            return int(res.get('filter-ident'))
        else:
            raise BittorrentError(res)

    def get_labels(self):
        return dict(self.get({'list': 1, 'getmsg': 1})['labels'])

    def get_torrents(self):
        return self._get_msgs('torrents', self.keys('TORRENT_'))

    def get_rss_filters(self):
        return self._get_msgs('rssfilters', self.keys('RSSFILTER_'))

    def set_priority(self, torrent_hash, priority, file_indices):
        return self.get({
            "action": "setprio",
            "hash": torrent_hash,
            "p": priority,
            "f": file_indices
        })

    def get_files(self, *torrent_hashes):
        files = self.get({
            'action': 'getfiles',
            'hash': torrent_hashes
        })['files']

        files = iter(files)
        files = dict(zip(files, files))

        return {
            torrent_hash: [
                dict(zip(self.keys('FILE_'), torrent_file))
                for torrent_file in torrent_files
            ]
            for torrent_hash, torrent_files in files.items()
        }

    def get_rss_feeds(self):
        qualities = self.consts()['RSSITEMQUALITYMAP']
        codecs = self.consts()['RSSITEMCODECMAP']

        feeds = self._get_msgs('rssfeeds', self.keys('RSSFEED_'))
        for feed in feeds:
            feed['items'] = [
                dict(zip(self.keys('RSSITEM_'), item))
                for item in feed['items']
            ]
            feed['items'] = [
                dict(
                    item,
                    quality=qualities[int(item['quality'])],
                    codec=codecs[int(item['codec'])]
                )
                for item in feed['items']
            ]

        return feeds

    def add_feed(self, name, url, directory):
        rss_ident = self.rss_update({
            'url': url,
            'alias': name,
            'subscribe': 1
        })

        filters = {
            rf['feed']: rf['id']
            for rf in self.get_rss_filters()
        }
        self.filter_update({
            'name': name,
            'filter-id': filters[rss_ident],
            'save-in': directory
        })

    @property
    @lru_cache()
    def Priority(self):
        return type(
            'Priority',
            (),
            {
                k.replace('FILEPRIORITY_', ''): v
                for k, v in self.consts().items()
                if k.startswith('FILEPRIORITY_')
            }
        )()


class OClient():
    def __init__(self, client):
        self.client = client

    @classmethod
    def new(cls, *args, **kwargs):
        return cls(Client(*args, **kwargs))

    def get_torrents(self):
        return [
            Torrent(self, meta)
            for meta in self.client.get_torrents()
        ]

    @property
    def Priority(self):
        return self.client.Priority

    def get_files(self, torrents):
        torrents = {torrent.hash: torrent for torrent in torrents}
        gen = self.client.get_files(list(torrents)).items()

        def internal():
            for torrent_hash, files in gen:
                torrent = torrents[torrent_hash]

                torrent.files = files

                yield torrent, torrent.files

        return dict(internal())


class Torrent:
    def __init__(self, client, meta):
        self.client = client
        self.meta = meta
        self._files = None

    def __repr__(self):
        return '<Torrent "{}">'.format(self.name)

    def __hash__(self):
        return hash(self.hash)

    def __getattr__(self, name):
        value = self.meta[name]
        setattr(self, name, value)
        return value

    @property
    def files(self):
        if self._files is None:
            self.files = self.client.get_files([self])
        return self._files

    @files.setter
    def files(self, files):
        if isinstance(files, dict):
            files = files[self]

        if not files:
            return

        if isinstance(files[0], dict):
            # this is if we're being passed a list of torrent files
            # that haven't been wrapped in TorrentFile yet
            self._files = [
                TorrentFile(self.client, self, idx, torrentfile)
                for idx, torrentfile in enumerate(files)
            ]
        else:
            # this is if we're being passed a list of TorrentFile
            self._files = files

    def set_priority(self, level, files):
        if not isinstance(files, list):
            files = [files]
        self.client.client.set_priority(
            self.hash,
            level,
            [file.idx for file in files]
        )


class TorrentFile:
    def __init__(self, client, torrent, idx, data):
        self.client = client
        self.torrent = torrent
        self.idx = idx
        self.data = data

    def is_skipped(self):
        return self.data['priority'] == self.client.Priority.SKIP

    @property
    def name(self):
        return self.data['name']

    def is_finished(self):
        return self.data['downloaded'] == self.data['size']

    def set_priority(self, level):
        self.torrent.set_priority(
            level,
            self
        )

    def __gt__(self, other):
        return self.name > other.name

    def __repr__(self):
        return '<TorrentFile "{}">'.format(self.name)


def main():
    __import__('ipdb').set_trace()
    client = OClient.new(
        # Client(
            'http://localhost:8081/gui/', auth=('admin', '20133')
            # )
    )

    torrents = client.get_torrents()

    for torrent in torrents:
        print(unidecode(torrent.name))
        for tf in torrent.files:
            print('\t', unidecode(tf.name))
        print()

if __name__ == '__main__':
    main()
