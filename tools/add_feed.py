import os
from urllib.parse import urlencode, quote

from autobit import Client


def add_rarbg_feed(client, name, directory, filter_kwargs):
    url = 'http://localhost:5555/{}?{}'.format(
        quote(name),
        urlencode(filter_kwargs)
    )

    return client.add_feed(name, url, directory)


def main():
    client = Client('http://localhost:8081/gui/', auth=('admin', '20133'))

    name = input('name> ')
    directory = input('directory> ')

    os.makedirs(directory, exist_ok=True)

    if input('rarbg[yn]> ') == 'n':
        client.add_feed(
            name,
            input('url> '),
            directory
        )
    else:
        add_rarbg_feed(
            client,
            name,
            directory,
            eval(input('filter dict> '))
        )


if __name__ == '__main__':
    main()
