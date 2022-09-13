import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import utils
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


def get_content(url, args, save_debug=False):
    if url.startswith('://'):
        url = url.replace('://', 'https://www.ft.com')

    if '/reports/' in url:
        # skip
        return None

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "host": "www.ft.com",
        "referrer": "https://www.google.com/",
        "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"101\", \"Microsoft Edge\";v=\"101\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "cross-site",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.53"
    }
    article_html = utils.get_url_html(url, headers=headers)
    if not article_html:
        return None
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    ld_json = None
    soup = BeautifulSoup(article_html, 'html.parser')
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        try:
            ld_json = json.loads(el.string)
            if re.search(r'NewsArticle|VideoObject', ld_json['@type']):
                break
        except:
            logger.warning('unable to load ld+json data in ' + url)
        ld_json = None

    if not ld_json:
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
    else:
        item['author']['name'] = 'Financial Times'

    if ld_json.get('image'):
        item['_image'] = ld_json['image']['url']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    if ld_json['@type'] == 'VideoObject':
        item['_video'] = ld_json['contentUrl']
        caption = '<a href="{}">{}</a>. {}'.format(item['url'], item['title'], item['summary'])
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', resize_image(ld_json['thumbnailUrl']), caption)
        if 'embed' not in args:
            el = soup.find(id='description')
            if el and el.p:
                item['content_html'] += str(el.p)
            el = soup.find(id='transcript')
            if el:
                item['content_html'] += el.decode_contents()

    elif ld_json.get('articleBody'):
        item['content_html'] = ''
        el = soup.find(class_='o-topper__visual')
        if not el:
            el = soup.find(class_='main-image')
        if el and len(el.contents) > 0:
            item['content_html'] += add_image(el)
        elif item.get('_image'):
            item['content_html'] += utils.add_image(resize_image(item['_image']))

        article_body = soup.find('div', attrs={"data-attribute": "article-content-body"})
        for el in article_body.find_all('div', class_='o-ads'):
            el.decompose()

        for el in article_body.find_all('aside'):
            el.decompose()

        for el in article_body.find_all(class_='n-content-layout'):
            print(el.get('data-layout-name'))
            if el.get('data-layout-name') == 'card':
                # Skip newsletter signups
                if not el.find('a', href=re.compile('https://ep\.ft\.com/newsletters/subscribe')):
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
                video_item = get_content(el.a['href'], {"embed": True}, False)
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

        item['content_html'] += re.sub(r'</figure>\s*<figure', '</figure><br/><figure', article_body.decode_contents())
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)


def test_handler():
    feeds = ['https://www.ft.com/rss/home',
             'https://www.ft.com/technology?format=rss',
             'https://www.ft.com/opinion?format=rss']
    for url in feeds:
        get_feed({"url": url}, True)
