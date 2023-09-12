import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    return '{}?w={}'.format(utils.clean_url(img_src), width)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    m = re.search(r'-(\d+)$', paths[-1])
    if not m:
        logger.warning('unable to parse post id from ' + url)
        return None

    post_url = '{}{}/{}'.format(site_json['wpjson_path'], site_json['posts_path'], m.group(1))
    post_json = utils.get_url_json(post_url)
    if post_json and save_debug:
        utils.write_file(post_json, './debug/post.json')

    article_url = '{}/mobile-apps/v1/article/{}'.format(site_json['wpjson_path'], m.group(1))
    article_json = utils.get_url_json(article_url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['post-id']
    item['url'] = article_json['permalink']
    item['title'] = article_json['headline']

    tz_est = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromisoformat(article_json['published-at'])
    dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt_utc.isoformat()
    item['_timestamp'] = dt_utc.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt_utc.strftime('%b'), dt_utc.day, dt_utc.year)

    dt_loc = datetime.fromisoformat(article_json['updated-at'])
    dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt_utc.isoformat()

    item['author'] = {}
    if article_json.get('byline'):
        item['author']['name'] = article_json['byline']
    elif post_json and post_json['_links'].get('author'):
        authors = []
        for link in post_json['_links']['author']:
            link_json = utils.get_url_json(link['href'])
            if link_json:
                authors.append(link_json['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for tag in article_json['tags']:
        item['tags'].append(tag['name'])

    item['summary'] = article_json['body-preview']

    lede = ''
    if article_json.get('featured-video'):
        if 'connatix_contextual_player' in article_json['featured-video']:
            m = re.search(r'playerId:"([^"]+)",mediaId:"([^"]+)"', re.sub(r'\s', '', article_json['featured-video']))
            if m:
                video_src = 'https://vid.connatix.com/pid-{}/{}/playlist.m3u8'.format(m.group(1), m.group(2))
                poster = 'https://img.connatix.com/pid-{}/{}/1_th.jpg?width=1000&format=jpeg&quality=60'.format(m.group(1), m.group(2))
                caption = []
                if article_json.get('featured-image'):
                    if article_json['featured-image'].get('caption'):
                        caption.append(article_json['featured-image']['caption'])
                    if article_json['featured-image'].get('credit'):
                        caption.append(article_json['featured-image']['credit'])
                lede += utils.add_video(video_src, 'application/x-mpegURL', poster, ' | '.join(caption))
        else:
            lede += utils.add_embed(article_json['featured-video'])

    if article_json.get('featured-image'):
        for img in article_json['featured-image']['crops']:
            if img['name'] == 'full':
                item['_image'] = img['url']
                if not lede:
                    caption = []
                    if article_json['featured-image'].get('caption'):
                        caption.append(article_json['featured-image']['caption'])
                    elif img.get('caption'):
                        caption.append(img['caption'])
                    if article_json['featured-image'].get('credit'):
                        caption.append(article_json['featured-image']['credit'])
                    elif img.get('credit'):
                        caption.append(img['credit'])
                    lede += utils.add_image(resize_image(img['url']), ' | '.join(caption))
                break

    if article_json.get('tagline'):
        lede = '<p><i>{}</i></p>'.format(article_json['tagline']) + lede

    if article_json.get('review_meta') and article_json['review_meta'].get('rating'):
        lede += '<h3>{}<br/>{}<br/><span style="font-size:1.5em;">{} / {}</span></h3>'.format(
            article_json['review_meta']['title'], article_json['review_meta']['artist'], article_json['review_meta']['rating'],
            article_json['review_meta']['rating_out_of'])

    soup = BeautifulSoup(article_json['body'], 'html.parser')

    for el in soup.find_all(class_='lrv-u-text-transform-uppercase'):
        el.string = el.string.upper()
        el.unwrap()

    for el in soup.find_all(id=re.compile(r'attachment_\d+')):
        img = el.find('img')
        if img:
            if 'alignleft' in el['class']:
                img['style'] = 'float:left; margin-right:8px;'
                el.parent.insert_after(BeautifulSoup('<div style="clear:left;"></div>', 'html.parser'))
            else:
                captions = []
                it = el.find(class_='wp-caption-text')
                if it:
                    captions.append(it.get_text())
                it = el.find(class_='rs-image-credit')
                if it:
                    captions.append(it.get_text())
                new_html = utils.add_image(resize_image(el.img['src']), ' | '.join(captions))
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()

    for el in soup.find_all(class_='post-content-image'):
        img = el.find('img')
        if img:
            if img.get('data-lazy-src'):
                img_src = img['data-lazy-src']
            else:
                img_src = img['src']
            captions = []
            it = el.find('cite')
            if it:
                captions.append(it.get_text())
                it.decompose()
            it = el.find('figcaption')
            if it:
                captions.insert(0, it.get_text())
            new_html = utils.add_image(resize_image(img_src), ' | '.join(captions))
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled post-content-image in ' + item['url'])

    for el in soup.find_all(class_='wp-block-embed'):
        new_html = ''
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled wp-block-embed in ' + item['url'])

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        if el.parent.name == 'b':
            el.parent.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.parent.decompose()
        else:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in soup.find_all('script'):
        new_html = ''
        if el.get('id') and 'connatix_contextual_player' in el['id']:
            m = re.search(r'playerId:"([^"]+)",mediaId:"([^"]+)"', re.sub(r'\s', '', el.string))
            if m:
                video_src = 'https://vid.connatix.com/pid-{}/{}/playlist.m3u8'.format(m.group(1), m.group(2))
                poster = 'https://img.connatix.com/pid-{}/{}/1_th.jpg?width=1000&format=jpeg&quality=60'.format(m.group(1), m.group(2))
                new_html = utils.add_video(video_src, 'application/x-mpegURL', poster)
            else:
                logger.warning('unhandled connatix_contextual_player in ' + item['url'])
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            el.decompose()

    item['content_html'] = lede + str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
