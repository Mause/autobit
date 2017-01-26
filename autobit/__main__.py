from . import OClient
from unidecode import unidecode


def main():
    client = OClient.new(
        'http://localhost:8081/gui/', auth=('admin', '20133')
    )

    torrents = client.get_torrents()

    for torrent in torrents:
        print(unidecode(torrent.name))
        for tf in torrent.files:
            print('\t', unidecode(tf.name))
        print()

if __name__ == '__main__':
    main()
