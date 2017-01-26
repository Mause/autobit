from pprint import pformat

from unidecode import unidecode

from .core import Client


pprint = lambda obj: print(unidecode(pformat(obj)))


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
