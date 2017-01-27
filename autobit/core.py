import re
import json
from functools import lru_cache
from operator import itemgetter

import attr
import requests
from slimit.parser import Parser


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

    def _ensure_token(self):
        if 'token' in self.session.params:
            return

        r = self.session.get(self.base_url + 'token.html')

        # this is bad practice, but is only used here
        self.session.params['token'] = re.search(r"'>(.*?)</", r.text).group(1)

    def get(self, params):
        self._ensure_token()
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
