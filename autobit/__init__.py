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
        return hash((self.__class__, self.hash))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __getattr__(self, name):
        value = self.meta[name]
        setattr(self, name, value)
        return value

    @property
    def files(self):
        if self._files is None:
            self.files = self.client.get_files([self])[self]
        return self._files

    @files.setter
    def files(self, files):

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

    def __hash__(self):
        return hash((self.torrent, self.idx, self.name))

    def __eq__(self, other):
        return hash(self) == hash(other)

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
