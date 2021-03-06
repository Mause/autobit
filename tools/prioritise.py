import time
import argparse
from fnmatch import fnmatch

from autobit import OClient


def prioritise_single(client, torrent, files):
    files = [
        file
        for file in files
        if not file.is_skipped()
    ]
    first_not_done = next(
        (
            file
            for file in files
            if not file.is_finished()
        ),
        None
    )
    if first_not_done is None:
        return  # all are done

    # reset all to lowest priority
    torrent.set_priority(client.Priority.LOW, files)

    # set next to high
    first_not_done.set_priority(client.Priority.HIGH)

    # set next four to normal
    idx = files.index(first_not_done)
    torrent.set_priority(client.Priority.NORMAL, files[idx+1:idx+5])


def prioritise_many(client, torrents):
    for torrent, files in client.get_files(torrents).items():
        prioritise_single(client, torrent, files)


def main(args):
    client = OClient(
        'http://localhost:8081', auth=('admin', '20133')
    )

    torrents = [
        torrent
        for torrent in client.get_torrents()
        if fnmatch(torrent.name, args.pattern)
    ]
    if not torrents:
        return

    if args.repeat is not None:
        while True:
            prioritise_many(client, torrents)
            time.sleep(args.repeat)
    else:
        prioritise_many(client, torrents)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pattern')
    parser.add_argument('-r', '--repeat', action='store', type=int)
    args = parser.parse_args()

    main(args)
