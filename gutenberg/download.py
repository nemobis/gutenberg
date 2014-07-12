#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import os
import tempfile
import zipfile

import requests
from path import path

from gutenberg import logger
from gutenberg.database import BookFormat, Format
from gutenberg.export import get_list_of_filtered_books, fname_for
from gutenberg.utils import (get_possible_urls_for_book,
                             download_file, FORMAT_MATRIX)


def resource_exists(url):
    r = requests.get(url, stream=True)
    return r.status_code == requests.codes.ok


def handle_zipped_epub(zippath,
                       book,
                       download_cache):

    clfn = lambda fn: os.path.join(*os.path.split(fn)[1:])

    def is_safe(fname):
        fname = clfn(fname)
        if path(fname).basename() == fname:
            return True
        return fname == os.path.join("images",
                                     path(fname).splitpath()[-1])


    zipped_files = []
    # create temp directory to extract to
    tmpd = tempfile.mkdtemp()
    with zipfile.ZipFile(zippath, 'r') as zf:
        # check that there is no insecure data (absolute names)
        if sum([1 for n in zf.namelist()
                if not is_safe(n)]):
            path(tmpd).rmtree_p()
            return False
        else:
            # zipped_files = [clfn(fn) for fn in zf.namelist()]
            zipped_files = zf.namelist()

        # extract files from zip
        zf.extractall(tmpd)

    # move all extracted files to proper locations
    for fname in zipped_files:
        # skip folders
        if not path(fname).ext:
            continue

        src = os.path.join(tmpd, fname)
        fname = path(fname).basename()

        if fname.endswith('.html') or fname.endswith('.htm'):
            dst = os.path.join(download_cache,
                               "{bid}.html".format(bid=book.id))
        else:
            dst = os.path.join(download_cache,
                               "{bid}_{fname}".format(bid=book.id,
                                                      fname=fname))
        try:
            path(src).move(dst)
        except Exception as e:
            import traceback
            print(e)
            print("".join(traceback.format_exc()))
            import ipdb; ipdb.set_trace()

    # delete temp directory
    path(tmpd).rmtree_p()


def download_all_books(url_mirror, download_cache,
                       languages=[], formats=[],
                       force=False):

    available_books = get_list_of_filtered_books(languages, formats)

    # ensure dir exist
    path(download_cache).mkdir_p()

    missings = []

    for book in available_books:

        logger.info("\tDownloading content files for Book #{id}"
                    .format(id=book.id))

        # apply filters
        if not formats:
            formats = FORMAT_MATRIX.keys()

        # HTML is our base for ZIM for add it if not present
        if not 'html' in formats:
            formats.append('html')

        for format in formats:

            fpath = os.path.join(download_cache, fname_for(book, format))

            # check if already downloaded
            if path(fpath).exists() and not force:
                logger.debug("\t\t{fmt} already exists at {path}"
                             .format(fmt=format, path=fpath))
                continue

            # retrieve corresponding BookFormat
            bfs = BookFormat.filter(book=book)

            if format == 'html':
                # patterns = ['{id}-h.zip', '{id}.html.noimages', '{id}.html.gen', 'salme10h.htm']
                patterns = ['mnsrb10h.htm', '8ledo10h.htm', 'tycho10f.htm', '8ledo10h.zip', 'salme10h.htm', '8nszr10h.htm', '{id}-h.html', '{id}.html.gen', '{id}-h.htm', '8regr10h.zip', '{id}.html.noimages', '8lgme10h.htm', 'tycho10h.htm', 'tycho10h.zip', '8lgme10h.zip', '8indn10h.zip', '8resp10h.zip', '20004-h.htm', '8indn10h.htm', '8memo10h.zip', 'fondu10h.zip', '{id}-h.zip', '8mort10h.zip']
                bfso = bfs
                bfs = bfs.join(Format).filter(Format.pattern << patterns)
                if not bfs.count():
                    from pprint import pprint as pp ; pp(list([(b.format.mime, b.format.images, b.format.pattern) for b in bfs]))
                    from pprint import pprint as pp ; pp(list([(b.format.mime, b.format.images, b.format.pattern) for b in bfso]))
                    import ipdb; ipdb.set_trace()
            else:
                bfs = bfs.filter(BookFormat.format << Format.filter(mime=FORMAT_MATRIX.get(format)))

            if not bfs.count():
                logger.debug("[{}] not avail. for #{}# {}"
                             .format(format, book.id, book.title))
                continue

            if bfs.count() > 1:
                try:
                    bf = bfs.join(Format).filter(Format.images == True).get()
                except:
                    bf = bfs.get()
            else:
                bf = bfs.get()

            logger.debug("[{}] Requesting URLs for #{}# {}"
                         .format(format, book.id, book.title))

            # retrieve list of URLs for format unless we have it in DB
            if bf.downloaded_from and not force:
                urls = [bf.downloaded_from]
            else:
                urld = get_possible_urls_for_book(book)
                urls = list(reversed(urld.get(FORMAT_MATRIX.get(format))))

            import copy
            allurls = copy.copy(urls)

            while(urls):
                url = urls.pop()

                if not resource_exists(url):
                    continue

                # HTML files are *sometime* available as ZIP files
                if url.endswith('.zip'):
                    zpath = "{}.zip".format(fpath)
                    download_file(url, zpath)

                    # extract zipfile
                    handle_zipped_epub(zippath=zpath, book=book,
                                       download_cache=download_cache)
                else:
                    download_file(url, fpath)

                # store working URL in DB
                bf.downloaded_from = url
                bf.save()

            if not bf.downloaded_from:
                logger.debug("NO FILE FOR #{}/{}".format(book.id, format))
                from pprint import pprint as pp ; pp(allurls)
                # import ipdb; ipdb.set_trace()
                missings.append(book.id)

    from pprint import pprint as pp ; pp(missings)
