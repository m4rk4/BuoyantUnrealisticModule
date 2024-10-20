import base64, json, re
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_cffi_requests
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    if '/__origami/' in img_src:
        return re.sub(r'width=\d+', 'width={}'.format(width), img_src)
    return 'https://www.ft.com/__origami/service/image/v2/images/raw/{}?source=next&fit=scale-down&width={}'.format(quote_plus(img_src), width)


def add_image(image_el):
    el = image_el.find('img')
    if el:
        img_src = resize_image(el['src'])
    else:
        logger.warning('unable to determine image src')
        return ''
    el = image_el.find('figcaption')
    if el:
        caption = el.decode_contents().strip()
        if not caption.startswith('©'):
            caption = caption.replace('©', '| ©')
    else:
        caption = ''
    return utils.add_image(img_src, caption)


def get_archive_content(url, title, args, site_json, save_debug):
    # TODO: utils.get_url_html often times out
    # page_html = utils.get_url_html('https://archive.is/' + url, use_proxy=True, use_curl_cffi=True)
    # if not page_html:
    #     return None
    r = curl_cffi_requests.get('https://archive.is/' + url, impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        return None
    page_html = r.text
    if save_debug:
        utils.write_file(page_html, './debug/archive.html')
    soup = BeautifulSoup(page_html, 'lxml')
    archive_links = []
    for el in soup.find_all('div', class_='TEXT-BLOCK'):
        if el.a['href'] not in archive_links:
            archive_links.append(el.a['href'])
    if len(archive_links) == 0:
        logger.warning(url + ' is not archived')
        return None
    archive_link = archive_links[-1]
    logger.debug('getting content from ' + archive_link)

    # TODO: utils.get_url_html often times out
    # page_html = utils.get_url_html(archive_link, use_proxy=True, use_curl_cffi=True)
    # if not page_html:
    #     return None
    r = curl_cffi_requests.get(archive_link, impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        return None
    page_html = r.text
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', attrs={"type": "application/ld+json"})
    if el:
        i = el.string.find('{')
        j = el.string.rfind('}') + 1
        ld_json = json.loads(el.string[i:j])
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')

        if title:
            if ld_json['headline'].lower() != title.lower() or (ld_json.get('alternativeHeadline') and ld_json['alternativeHeadline'].lower() != title.lower()):
                logger.warning('{} does not match title for {}'.format(archive_link, url))

        item = {}
        el = soup.find('old-meta', attrs={"property": "og:url"})
        if el:
            item['url'] = el['content']
        else:
            item['url'] = url
        item['id'] = list(filter(None, urlsplit(item['url']).path[1:].split('/')))[-1]
        item['title'] = ld_json['headline']

        dt = datetime.fromisoformat(ld_json['datePublished'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if ld_json.get('dateModified'):
            dt = datetime.fromisoformat(ld_json['dateModified'])
            item['date_modified'] = dt.isoformat()

        item['authors'] = []
        if ld_json.get('author'):
            if isinstance(ld_json['author'], dict):
                if ld_json['author'].get('name'):
                    item['authors'].append({"name": ld_json['author']['name']})
            elif isinstance(ld_json['author'], list):
                item['authors'] = [{"name": x['name']} for x in ld_json['author']]
        else:
            for el in soup.find_all('old-meta', attrs={"property": "article:author"}):
                if el['content'].strip():
                    item['authors'].append({"name": el['content']})
        if not item['authors'] and ld_json.get('publisher') and ld_json['publisher'].get('name'):
            item['authors'].append({"name": ld_json['publisher']['name']})
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }

        item['tags'] = []
        for el in soup.select('h2'):
            if re.search(r'follow the topics', el.get_text(), flags=re.I):
                it = el.find_next_sibling()
                if it.name == 'ul':
                    for li in it.find_all('li'):
                        item['tags'].append(li.a.string.strip())
        if len(item['tags']) == 0:
            del item['tags']

        item['content_html'] = ''
        if ld_json.get('description'):
            item['summary'] = ld_json['description']
            item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

        if ld_json.get('image') and ld_json['image'].get('url'):
            item['image'] = re.sub(r'width=\d+', 'width=1200', ld_json['image']['url'])
            item['content_html'] += utils.add_image(item['image'])

        body = soup.find('article', id='article-body')
        for el in body.find_all(recursive=False):
            if el.name == 'div':
                it = el.find('div', attrs={"old-src": re.compile(r'https://flo\.uri\.sh')})
                if it:
                    new_html = utils.add_embed(it['old-src'])
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                elif el.find('a', {"href": re.compile(r'https://ep\.ft\.com/newsletters/subscribe\?')}):
                    el.decompose()
                elif el.find('button', attrs={"aria-label": re.compile(r'^Play video .* FT Tech', flags=re.I)}):
                    it = el.find('button', attrs={"aria-label": re.compile(r'^Play video .* FT Tech', flags=re.I)})
                    q = re.sub(r'^Play video ', '', it['aria-label'])
                    results = utils.search_for(q)
                    print(results)
                    if results:
                        new_html = utils.add_embed(results[0]['href'])
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        el.replace_with(new_el)
                    else:
                        el.decompose()
                else:
                    txt = el.get_text().strip()
                    if txt and not re.search(r'recommended newsletters|this( article)? is an on-site version|please send gossip', txt, flags=re.I):
                        el.attrs = {}
                        el.name = 'p'
                    else:
                        el.decompose()
            elif el.name == 'figure' and el.img:
                img_src = utils.clean_url(el.img['new-cursrc']) + '?source=next-article&fit=scale-down&quality=highest&width=1200&dpr=1'
                captions = []
                for it in el.select('figcaption > span'):
                    captions.append(it.decode_contents())
                new_html = utils.add_image(img_src, ' | '.join(captions))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            elif el.name == 'blockquote':
                it = el.find('div', attrs={"style": re.compile(r'margin-top:-12px')})
                if it:
                    new_html = utils.add_pullquote(it.decode_contents(), el.footer.decode_contents())
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                else:
                    it = el.find('span', attrs={"style": re.compile(r'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDI0IDEwMjQiPjxzdHlsZT4qe2ZpbGw6IzFBMTgxNyFpbXBvcnRhbnQ7fTwvc3R5bGU\+PHBhdGggZD0iTTQ5OS44IDU5NC4zYzAgNzcuMy02OCAxMzYtMTM5LjIgMTM2LTg1IDAtMTYwLjgtNTQuMS0xNjAuOC0xNzEuNiAwLTEzNy42IDExNy41LTI1NSAyODkuMi0yNjcuNGw0LjYgMjkuNGMtMTA4LjIgMTctMTY3IDcxLjEtMTY3IDEzNy42IDg1LjEtMTUuNCAxNzMuMiAzNS42IDE3My4yIDEzNnptMzI0LjcgMGMwIDc3LjMtNjggMTM2LTEzOS4yIDEzNi04NSAwLTE2MC44LTU0LjEtMTYwLjgtMTcxLjYgMC0xMzcuNiAxMTcuNS0yNTUgMjg5LjItMjY3LjRsNC42IDI5LjRjLTEwOC4yIDE3LTE2NyA3MS4xLTE2NyAxMzcuNiA4NS4xLTE1LjQgMTczLjIgMzUuNiAxNzMuMiAxMzZ6Ii8\+PC9zdmc\+Cg==')})
                    if it:
                        # TODO: pullquote author?
                        new_html = utils.add_pullquote(el.div.decode_contents())
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        el.replace_with(new_el)
                    else:
                        logger.warning('unhandled blockquote in ' + item['url'])
            elif el.name == 'ul':
                new_html = '<ul>'
                for it in el.find_all('span', string='•'):
                    it.decompose()
                for it in el.find_all('li'):
                    new_html += '<li>' + it.div.decode_contents() + '</li>'
                new_html += '</ul>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            elif el.name == 'h2':
                el.attrs = {}
            elif el.name == 'hr':
                new_html = '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            elif el.name == 'aside' and el.find('div', string=re.compile(r'Recommended')):
                el.decompose()
            else:
                logger.warning('unhandled {} in {}'.format(el.name, item['url']))

        for el in body.find_all('a', href=re.compile(r'^https://archive.is')):
            el['href'] = re.sub(r'^https://archive.is/.*?/https:', 'https:', el['href'])

        item['content_html'] += body.decode_contents()
        return item


def get_content(url, args, site_json, save_debug=False):
    if url.startswith('://'):
        url = url.replace('://', 'https://www.ft.com')

    if '/reports/' in url:
        # skip
        return None

    r = curl_cffi_requests.get(url, impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        return None
    page_html = r.text
    if save_debug:
        utils.write_file(page_html, './debug/page.html')
    soup = BeautifulSoup(page_html, 'lxml')

    split_url = urlsplit(url)

    if '/content/' in split_url.path and 'noarchive' not in args:
        el = soup.select('h1 > blockquote')
        if el:
            title = el[0].get_text().strip()
        else:
            title = ''
        item = get_archive_content(url, title, args, site_json, save_debug)
        if item:
            return item

    ld_json = None
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        try:
            ld_json = json.loads(el.string)
            if re.search(r'Article|VideoObject', ld_json['@type']):
                break
        except:
            logger.warning('unable to load ld+json data in ' + url)
        ld_json = None

    if not ld_json:
        el = soup.find('script', id='page-kit-app-context')
        if el:
            context_json = json.loads(el.string)
            if context_json['contentType'] == 'podcast':
                logger.warning('podcast content')
                return None
        logger.warning('unable to find ld+json data in ' + url)
        return None

    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = url

    if ld_json.get('mainEntityofPage'):
        item['url'] = ld_json['mainEntityofPage']
    elif ld_json.get('url'):
        item['url'] = ld_json['url']
    else:
        item['url'] = url

    if ld_json.get('headline'):
        item['title'] = ld_json['headline']
    elif ld_json.get('name'):
        item['title'] = ld_json['name']

    dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if ld_json.get('author'):
        if isinstance(ld_json['author'], dict):
            if ld_json.get('author') and ld_json['author'].get('name'):
                item['author']['name'] = ld_json['author']['name']
        elif isinstance(ld_json['author'], list):
            authors = []
            for author in ld_json['author']:
                authors.append(author['name'])
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif ld_json.get('publisher') and ld_json['publisher'].get('name'):
        item['author']['name'] = ld_json['publisher']['name']
    if not item['author'].get('name') or item['author']['name'] == 'Staff Writer':
        el = soup.find(attrs={"data-trackable": "byline"})
        if el:
            item['author']['name'] = el.get_text()
    if not item['author'].get('name'):
        if ld_json.get('publisher'):
            item['author']['name'] = ld_json['publisher']['name']
        else:
            item['author']['name'] = urlsplit(url).netloc

    if ld_json.get('image'):
        if isinstance(ld_json['image'], dict):
            item['_image'] = ld_json['image']['url']
        elif isinstance(ld_json['image'], str):
            item['_image'] = ld_json['image']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    el = soup.find('meta', attrs={"name": "keywords"})
    if el:
        item['tags'] = list(map(str.strip, el['content'].split(',')))
    else:
        item['tags'] = []
        for el in soup.find_all('a', class_='concept-list__concept'):
            item['tags'].append(el.get_text().strip())
        if not item.get('tags'):
            del item['tags']

    if ld_json['@type'] == 'VideoObject':
        item['_video'] = ld_json['contentUrl']
        caption = '<a href="{}">{}</a>. {}'.format(item['url'], item['title'], item['summary'])
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', resize_image(ld_json['thumbnailUrl']), caption, use_videojs=True)
        if 'embed' not in args:
            el = soup.find(id='description')
            if el and el.p:
                item['content_html'] += str(el.p)
            el = soup.find(id='transcript')
            if el:
                item['content_html'] += el.decode_contents()
        return item

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if ld_json.get('articleBody'):
        article_body = soup.find(['article', 'div'], attrs={"data-attribute": "article-content-body"})
        for el in article_body.find_all('div', class_='o-ads'):
            el.decompose()

        for el in article_body.find_all('aside'):
            el.decompose()

        for el in article_body.find_all(class_='n-content-layout'):
            #print(el.get('data-layout-name'))
            if el.get('data-layout-name') == 'card':
                # Skip newsletter signups
                if not el.find('a', href=re.compile(r'https://ep\.ft\.com/newsletters/subscribe')):
                    img = el.find('img')
                    if img:
                        new_html = '<table><tr><td style="vertical-align:top;"><img src="{}" style="width:240px;"/></td><td style="vertical-align:top;">'.format(resize_image(img['src'], 240))
                    else:
                        new_html = '<blockquote>'
                    it = el.find('h2')
                    if it:
                        new_html += '<strong>{}</strong><br/>'.format(it.get_text())
                    for it in el.find_all('p'):
                        new_html += it.decode_contents() + '<br/><br/>'
                    new_html = new_html[:-10]
                    if img:
                        new_html += '</td></tr></table>'
                    else:
                        new_html = '</blockquote>'
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_before(new_el)
            else:
                for it in el.find_all(class_=['n-content-image', 'n-content-picture']):
                    new_html = add_image(it)
                    if new_html:
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        el.insert_before(new_el)
            el.decompose()

        for el in article_body.find_all(class_=['n-content-image', 'n-content-picture']):
            new_html = add_image(el)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_before(new_el)
                el.decompose()

        for el in article_body.find_all(class_='n-content-video'):
            if 'n-content-video--internal' in el['class']:
                video_item = get_content(el.a['href'], {"embed": True}, site_json, False)
                if video_item:
                    new_el = BeautifulSoup(video_item['content_html'], 'html.parser')
                    el.insert_before(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled n-content-video--internal in ' + item['url'])
            elif 'n-content-video--youtube' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_before(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled n-content-video--youtube in ' + item['url'])
            else:
                logger.warning('unhandled n-content-video in ' + item['url'])

        for el in article_body.find_all(class_='n-content-tweet'):
            it = el.find_all('a')
            new_html = utils.add_embed(it[-1]['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in article_body.find_all(class_='n-content-pullquote'):
            it = el.find(class_='n-content-pullquote__footer')
            if it:
                author = it.get_text()
                it.decompose()
            else:
                author = ''
            it = el.find(class_='n-content-pullquote__content')
            if it:
                new_html = utils.add_pullquote(it.decode_contents().strip(), author)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_before(new_el)
                el.decompose()

        for el in article_body.find_all(class_=re.compile('n-content-heading')):
            el.attrs = {}

        for el in article_body.find_all('experimental'):
            el.unwrap()

        item['content_html'] = ''
        if article_body.find().name != 'figure':
            el = soup.find(class_='o-topper__standfirst')
            if el:
                item['content_html'] += '<p><em>' + el.decode_contents() + '</em></p>'
            el = soup.find(class_='o-topper__visual')
            if not el:
                el = soup.find(class_='main-image')
            if el and len(el.contents) > 0:
                item['content_html'] += add_image(el)
            elif item.get('_image'):
                item['content_html'] += utils.add_image(resize_image(item['_image']))

        item['content_html'] += article_body.decode_contents()

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
