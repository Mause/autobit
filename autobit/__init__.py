from pprint import pformat

from unidecode import unidecode

from .core import Client


pprint = lambda obj: print(unidecode(pformat(obj)))


class OClient():
    def __init__(self, base_url, session=None, auth=None):
        self.client = Client(base_url, session, auth)

    @classmethod
    def from_raw_client(cls, client):
        return cls(client.base_url, client.session, client.session.auth)

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

        for hs, files in gen:
            torrents[hs].files = [
                TorrentFile(self, torrents[hs], idx, torrentfile)
                for idx, torrentfile in enumerate(files)
            ]

        return {
            torrents[hs]: torrents[hs].files
            for hs, files in gen
        }

    def get_peers(self, torrents):
        torrents = {torrent.hash: torrent for torrent in torrents}
        peers = self.client.get_peers(list(torrents))

        return {
            torrents[hash]: [
                Peer(peer)
                for peer in peers
            ]
            for hash, peers in peers.items()
        }


class Torrent:
    def __init__(self, client, meta):
        self.client = client
        self.meta = meta
        self._files = None

    def __repr__(self):
        return '<Torrent "{}">'.format(self.name)

    def __hash__(self):
        return hash((self.__class__, self.hash))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __getattr__(self, name):
        try:
            value = self.meta[name]
        except KeyError:
            raise AttributeError(name)
        else:
            setattr(self, name, value)
            return value

    def get_peers(self):
        return self.client.get_peers([self])[self]

    @property
    def files(self):
        if self._files is None:
            self.files = self.client.get_files([self])[self]
        return self._files

    @files.setter
    def files(self, files):
        self._files = files

    def set_priority(self, level, files):
        if not isinstance(files, list):
            files = [files]
        self.client.client.set_priority(
            self.hash,
            level,
            [file.idx for file in files]
        )

    def refresh(self):
        self._files = None


class TorrentFile:
    def __init__(self, client, torrent, idx, data):
        self.client = client
        self.torrent = torrent
        self.idx = idx
        self.data = data

    def is_skipped(self):
        return self.get_priority() == self.client.Priority.SKIP

    def __hash__(self):
        return hash((self.torrent, self.idx, self.name))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def refresh(self):
        self.torrent.refresh()
        self.data = self.torrent.files[self.idx].data

    @property
    def name(self):
        return self.data['name']

    def is_finished(self):
        return self.data['downloaded'] == self.data['size']

    def get_priority(self):
        return self.client.Priority(self.data['priority'])

    def set_priority(self, level):
        self.torrent.set_priority(
            level,
            self
        )

    def __gt__(self, other):
        return self.name > other.name

    def __repr__(self):
        return '<TorrentFile "{}">'.format(self.name)


class Peer:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, name):
        try:
            value = self.data[name]
        except KeyError:
            raise AttributeError(name)
        else:
            setattr(self, name, value)
            return value

    def __repr__(self):
        return '<Peer "{}" "{}">'.format(
            self.data['client'],
            self.data['revdns'] or self.data['ip']
        )
