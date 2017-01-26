import os

from autobit import Client


def main():
    client = Client('http://localhost:8081/gui/', auth=('admin', '20133'))
    client.get_torrents()

    name = input('name> ')
    directory = input('directory> ')

    os.makedirs(directory, exist_ok=True)

    client.add_feed(
        name,
        input('url> '),
        directory
    )


if __name__ == '__main__':
    main()
