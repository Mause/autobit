import re
import enum
import json
from functools import lru_cache
from operator import itemgetter
from contextlib import redirect_stderr

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


class NoSuchTorrent(BittorrentError):
    pass


def paired(iterable):
    # given
    # [1, 2, 3, 4, 5, 6]
    # returns an iterator yielding
    # [(1, 2), (3, 4), (5, 6)]
    iterable = iter(iterable)
    return zip(iterable, iterable)


def make_items(keys, items):
    return [
        dict(zip(keys, item))
        for item in items
    ]


class Client:
    def __init__(self, base_url, session=None, auth=None):
        self.session = session or requests.Session()
        if auth:
            self.session.auth = auth

        if not base_url.endswith('/gui/'):
            base_url += '/gui/'

        self.base_url = base_url
        self._cached_consts = None

    def _ensure_token(self):
        if 'token' in self.session.params:
            return

        r = self.session.get(self.base_url + 'token.html')

        # this is bad practice, but is only used here
        self.session.params['token'] = re.search(r"'>(.*?)</", r.text).group(1)

    def get(self, params):
        self._ensure_token()

        params = {
            key: (
                value.value
                if isinstance(value, enum.Enum)
                else
                value
            )
            for key, value in params.items()
        }

        r = self.session.get(self.base_url, params=params).json()
        r.pop('build')
        return r

    def _get_msgs(self, key, keys):
        return make_items(keys, self.get({'list': 1, 'getmsg': 1})[key])

    def consts(self):
        if self._cached_consts is None:
            self._cached_consts = self._consts()
        return self._cached_consts

    def _consts(self):
        js = self.session.get(self.base_url + 'constants.js')

        with redirect_stderr(open('NUL', 'w')):
            parser = Parser()

        root = parser.parse(js.text)

        constants = root.children()[0].children()[0].initializer.properties
        return {
            assign.left.value: _load(assign.right)
            for assign in constants
        }

    @lru_cache()
    def keys_with_values(self, prefix):
        constants = self.consts()

        return {
            key[len(prefix):]: value
            for key, value in constants.items()
            if key.startswith(prefix)
        }

    @lru_cache()
    def keys(self, prefix):
        constants = self.keys_with_values(prefix)
        return tuple(
            key.lower()
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

    def get_files(self, torrent_hashes):
        files = self.get({
            'action': 'getfiles',
            'hash': torrent_hashes
        }).get('files')

        if files is None:
            raise NoSuchTorrent()

        keys = self.keys('FILE_')
        return {
            torrent_hash: make_items(keys, torrent_files)
            for torrent_hash, torrent_files in paired(files)
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

    def __getattr__(self, name):
        if name == 'Priority':
            self.Priority = self._make_Priority()
            return self.Priority
        else:
            raise AttributeError

    def get_peers(self, torrent_hash):
        torrent_peers = self.get({
            'action': 'getpeers',
            'hash': torrent_hash
        }).get('peers')

        if not torrent_peers:
            raise NoSuchTorrent()

        keys = self.keys('PEER_')
        return {
            hash: make_items(keys, peers)
            for hash, peers in paired(torrent_peers)
        }

    def _make_enum_from_consts(self, name, prefix):
        return enum.IntEnum(
            name,
            self.keys_with_values(prefix)
        )

    def _make_Priority(self):
        return self._make_enum_from_consts(
            'Priority',
            'FILEPRIORITY_'
        )
