import json, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_image(el, gallery=False):
    print(el)
    if gallery:
        it = el.find(class_='img-gallery-thumbnail-img')
    else:
        it = el.find(attrs={"data-img-url": True})
    if it.get('data-img-caption'):
        caption = re.sub('^"|"$', '', it['data-img-caption'])
        if caption == 'null':
            caption = ''
    else:
        caption = ''
    return utils.add_image(it['data-img-url'], caption)


def get_content(url, args, save_debug=False):
    # Sites: https://www.valnetinc.com/en/publishing-detail#our_brand
    split_url = urlsplit(url)
    article_json = utils.get_url_json('{}://{}/fetch/next-article{}'.format(split_url.scheme, split_url.netloc, split_url.path))
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    soup = BeautifulSoup(article_json['html'], 'html.parser')

    item = {}
    if article_json.get('gaCustomDimensions'):
        item['id'] = article_json['gaCustomDimensions']['postID']
        item['url'] = article_json['gaCustomDimensions']['location']
        item['title'] = article_json['gaCustomDimensions']['title']

        el = soup.find('time')
        if el:
            dt = datetime.fromisoformat(el['datetime'].replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(article_json['gaCustomDimensions']['datePublished'], '%Y%m%d').replace(tzinfo=timezone.utc)
        if dt:
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

        el = soup.find('a', class_='author')
        if el:
            item['author'] = {"name": el.get_text().strip()}
        else:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['gaCustomDimensions']['displayAuthors']))

        item['tags'] = list(filter(None, article_json['gaCustomDimensions']['tags'].split('|')))

        el = soup.find(class_='heading_excerpt')
        if el:
            item['summary'] = el.get_text()

    else:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        page_soup = BeautifulSoup(page_html, 'html.parser')
        ld_json = None
        for el in page_soup.find_all('script', attrs={"type": "application/ld+json"}):
            ld_json = json.loads(el.string)
            if ld_json.get('@type') and ld_json['@type'] == 'Article':
                break
            ld_json = None
        if not ld_json:
            logger.warning('unable to find ld+json data in ' + url)
            return None
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')

        item['id'] = ld_json['mainEntityOfPage']['@id']
        item['url'] = ld_json['mainEntityOfPage']['@id']
        item['title'] = ld_json['headline']

        dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

        authors = []
        for it in ld_json['author']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        if ld_json.get('articleSection'):
            item['tags'] = ld_json['articleSection'].copy()

        if ld_json.get('description'):
            item['summary'] = ld_json['description']

        if ld_json.get('image'):
            item['_image'] = ld_json['image']['url']

    item['content_html'] = ''
    if item.get('summary'):
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    el = soup.find(class_='heading_image')
    if el:
        item['_image'] = el['data-img-url']
        caption = re.sub('^"|"$', '', el['data-img-caption'])
        if caption == 'null':
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)

    body = soup.find(id='article-body')
    if body:
        # Remove comment sections
        for el in body.find_all(text=lambda text: isinstance(text, Comment)):
            el.extract()

        for el in body.find_all(class_=re.compile('ad-even|ad-odd|ad-zone|affiliate-sponsored')):
            el.decompose()

        for el in body.find_all(id='article-waypoint'):
            el.decompose()

        for el in body.find_all(class_=re.compile('next-single|related-single')):
            if el.parent and el.parent.name == 'p':
                el.parent.decompose()

        for el in body.find_all(class_='article__gallery'):
            new_html = ''
            for it in el.find_all(class_='gallery__images__item'):
                new_html += add_image(it, True)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='body-img'):
            new_html = add_image(el)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='w-rich'):
            new_html = ''
            if 'w-twitter' in el['class']:
                it = el.find(class_='twitter-tweet')
                if it.name == 'blockquote':
                    links = it.find_all('a')
                    new_html = utils.add_embed(links[-1]['href'])
                else:
                    new_html = utils.add_embed(utils.get_twitter_url(it['id']))
            elif 'w-youtube' in el['class']:
                new_html = utils.add_embed('https://www.youtube.com/embed/' + el['id'])
            elif 'w-instagram' in el['class']:
                it = el.find(class_='instagram-media')
                if it:
                    new_html = utils.add_embed(it['data-instgrm-permalink'])
            elif 'w-spotify' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
                else:
                    new_html = utils.add_embed(el['id'])
            elif 'w-reddit' in el['class']:
                it = el.find('a')
                new_html = utils.add_embed(it['href'])
            elif 'w-twitch' in el['class']:
                new_html = utils.add_embed('https://player.twitch.tv/?video=' + el['id'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled {} in {}'.format(el['class'], item['url']))

        for el in body.find_all('img', attrs={"alt": True}):
            new_html = utils.add_image(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        item['content_html'] += body.decode_contents()

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
