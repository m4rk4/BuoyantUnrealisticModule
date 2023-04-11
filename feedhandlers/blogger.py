import html, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)

def resize_image(img_src, width=1000):
    if img_src.startswith('//'):
        img_src = 'https:' + img_src
    if not img_src.startswith('https://blogger.googleusercontent.com/img/'):
        return img_src
    # https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhwtLj_nuoLbKbXR7DByAzp84su69-e32KGUm3OErdFCg0Aw1taNBqlS1-9tjrQyZlNQLsCiyT5RFbbR1SP4ckWz0pXsvXGqoVzhQRPs8LdPDeJQpwoBrr0zQ13kuwf3KAh3HzbzBmvx9FTdS82T0e7GCj_cZ1ujeOhhT1gUJDPMIrckJnODRs/s523/Screenshot%202023-03-17%209.30.31%20AM.png
    m = re.search(r'/s\d+/', img_src)
    if m:
        return img_src.replace(m.group(0), '/w{}/'.format(width))
    # https://blogger.googleusercontent.com/img/a/AVvXsEj16pzlwRCliEU_DIJSclc5FFqQFMnJRCL1M88m_j6wrr5uhR46ppd0NvDOCXw9EtaqvhR_vRsCGhsmZ63Z6ep0jESkTW2N46KXvKvEmeB2-8IYrGwngR70xTYZIxR7PDrLAV-RxCkxi5Wj56YIjfe7fKXZvXNnoLssWMhgJXoW2ocR_kASCZE=s72-w640-c-h410
    m = re.search(r'=[swch\-\d]+$', img_src)
    if m:
        return img_src.replace(m.group(0), '=w{}'.format(width))
    return img_src


def get_content(url, args, site_json, save_debug=False, module_format_content=None):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    m = re.search(r'\'blogId\':\s?\'(\d+)\'', page_html)
    if m:
        blog_id = m.group(1)
    else:
        logger.warning('unknown blogId in ' + url)
        return None
    m = re.search(r'\'postId\':\s?\'(\d+)\'', page_html)
    if m:
        post_id = m.group(1)
    else:
        logger.warning('unknown postId in ' + url)
        return None

    post_json = utils.get_url_json('https://www.blogger.com/feeds/{}/posts/default/{}?alt=json'.format(blog_id, post_id))
    if not post_json:
        return None

    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_id
    item['url'] = url
    item['title'] = post_json['entry']['title']['$t']

    dt = datetime.fromisoformat(post_json['entry']['published']['$t']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['entry']['updated']['$t']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    if post_json['entry'].get('author'):
        authors = []
        for it in post_json['entry']['author']:
            authors.append(it['name']['$t'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json['entry'].get('category'):
        item['tags'] = []
        for it in post_json['entry']['category']:
            item['tags'].append(it['term'])

    if post_json['entry'].get('media$thumbnail'):
        item['_image'] = resize_image(post_json['entry']['media$thumbnail']['url'])

    if post_json['entry'].get('summary'):
        item['summary'] = post_json['entry']['summary']

    if post_json['entry'].get('content'):
        content = BeautifulSoup(post_json['entry']['content']['$t'], 'html.parser')
    else:
        soup = BeautifulSoup(page_html, 'lxml')
        content = soup.find(class_='post-body')
        if not content:
            logger.warning('unable to determine post content in ' + item['url'])
            return item

    for el in content.find_all('img'):
        img_src = resize_image(el['src'])
        el_parent = el
        if el.parent and el.parent.name == 'a':
            el_parent = el.parent
            link = el.parent['href']
        else:
            link = ''
        caption = ''
        it = el.find_parent(class_='tr-caption-container')
        if it:
            if it.parent and it.parent.name == 'div':
                el_parent = it.parent
            else:
                el_parent = it
            it = it.find(class_='tr-caption')
            if it:
                caption = it.decode_contents()
        it = el.find_parent(class_='separator')
        if it:
            el_parent = it
        if el_parent.parent and el_parent.parent.name == 'p':
            el_parent = el_parent.parent
        if not caption:
            it = el_parent.find(class_='cite')
            if it and it.get('class') and 'cite' in it['class']:
                caption = it.decode_contents()
                it.decompose()
        new_html = utils.add_image(img_src, caption, link=link)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el_parent.insert_after(new_el)
        el_parent.decompose()

    for el in content.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in content.find_all('blockquote'):
        if el.get('class'):
            new_html = ''
            if 'twitter-tweet' in el['class']:
                it = el.find_all('a')
                new_html = utils.add_embed(it[-1]['href'])
            elif 'tiktok-embed' in el['class']:
                new_html = utils.add_embed(el['cite'])
            elif 'reddit-embed-bq' in el['class']:
                it = el.find('a')
                new_html = utils.add_embed(it['href'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled blockquote class {} in {}'.format(el['class'], item['url']))
        else:
            it = el.find('span', attrs={"style": re.compile(r'font-size:\s?x-small;')})
            if it:
                i = it.find('i')
                if i:
                    author = i.decode_contents()
                else:
                    author = it.decode_contents()
                author = re.sub(r'[\-]{2,}', '', author).strip()
                it.decompose()
                it = el.find('b')
                if it:
                    quote = it.decode_contents()
                else:
                    quote = el.decode_contents()
                new_html = utils.add_pullquote(quote, author)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in content.find_all('pre', class_='microcode'):
        el.attrs = {}
        el['style'] = 'margin-left:2em; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;'

    for el in content.find_all(['script', 'style']):
        el.decompose()

    item['content_html'] = content.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
