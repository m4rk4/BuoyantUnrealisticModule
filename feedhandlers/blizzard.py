import json, re
import dateutil.parser
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    detail_url = 'https://news.blizzard.com/en-us/blog/detail?blogId={}&community=all&full=false'.format(paths[2])
    detail_json = utils.get_url_json(detail_url)
    if not detail_json:
        return None
    if save_debug:
        utils.write_file(detail_json, './debug/debug.json')

    item = {}
    item['id'] = detail_json['blogId']
    item['url'] = url
    item['title'] = detail_json['blogTitle']

    soup = BeautifulSoup(detail_json['html'], 'html.parser')

    el = soup.find('time', attrs={"pubdate": "pubdate"})
    if el:
        dt = dateutil.parser.parse(el['timestamp'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": "Blizzard Entertainment"}

    item['tags'] = [detail_json['community']]

    item['content_html'] = ''
    el = soup.find(class_='ArticleDetail-headingImageBlock')
    if el:
        it = el.find('img')
        if it:
            item['_image'] = 'https:' + it['src']
            item['content_html'] += utils.add_image(item['_image'])

    content = soup.find(class_='ArticleDetail-content')
    if content:
        for el in content.find_all(text=lambda text: isinstance(text, Comment)):
            el.extract()

        for el in content.find_all(['style', 'script']):
            el.decompose()

        for el in content.find_all(class_='image'):
            it = el.find('img')
            if it:
                img_src = it['src']
                caption = ''
                fig = el.find_parent('figure')
                if fig:
                    it = fig.find('figcaption')
                    if it:
                        caption = it.get_text().strip()
                new_html = utils.add_image(img_src, caption)
                new_el = BeautifulSoup(new_html, 'html.parser')
                if fig:
                    fig.insert_after(new_el)
                    fig.decompose()
                else:
                    el.insert_after(new_el)
                    el.decompose()

        for el in content.find_all('iframe'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and (el.parent.name == 'div' or el.parent.name == 'p'):
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()

        for el in content.find_all('video'):
            video_src = el['src']
            caption = ''
            fig = el.find_parent('figure')
            if fig:
                it = fig.find('figcaption')
                if it:
                    caption = it.get_text().strip()
            new_html = utils.add_video(video_src, 'video/mp4', '', caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            if fig:
                fig.insert_after(new_el)
                fig.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()

        item['content_html'] += content.decode_contents()
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 1:
        list_json = utils.get_url_json('https://news.blizzard.com/en-us/blog/list?pageNum=1&pageSize=10&community=all')
    else:
        list_json = utils.get_url_json('https://news.blizzard.com/en-us/blog/list?pageNum=1&pageSize=10&community={}'.format(paths[1]))
    if not list_json:
        return None
    if save_debug:
        utils.write_file(list_json, './debug/feed.json')

    soup = BeautifulSoup(list_json['html'], 'html.parser')

    n = 0
    feed_items = []
    for article in soup.find_all('article'):
        article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article.a['href'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
          if utils.filter_item(item, args) == True:
            feed_items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['title'] = list_json['pageTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


