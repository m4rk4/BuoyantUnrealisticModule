import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    m = re.search(r'-(\d+)$', split_url.path)
    if not m:
        logger.warning('unable to determine post id in ' + url)
        return None
    post_json = utils.get_url_json('https://www.theepochtimes.com/gapi/posts/' + m.group(1))
    if not post_json:
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = 'https://www.theepochtimes.com' + post_json['uri']
    item['title'] = post_json['title']

    dt = datetime.fromtimestamp(post_json['publishedAt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(post_json['updatedAt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in post_json['authors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json.get('terms'):
        item['tags'] = []
        for it in post_json['terms']:
            item['tags'].append(it['name'])
    elif post_json.get('primaryTerm'):
        item['tags'] = [post_json['primaryTerm']['name']]

    item['content_html'] = ''
    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['excerpt'])

    if post_json.get('thumbnail'):
        item['_image'] = post_json['thumbnail']['original']
        item['content_html'] += utils.add_image(post_json['thumbnail']['original'], post_json['thumbnail'].get('caption'))

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    if post_json.get('audio'):
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen to the article</a></span></div>'.format(
            post_json['audio']['url'], config.server)

    for content in post_json['content']:
        if content['type'] == 'p':
            if content.get('text'):
                m = re.search(r'^(<h\d>.+?</h\d>)(.*)', content['text'].strip())
                if m:
                    item['content_html'] += m.group(1) + '<p>' + m.group(2) + '</p>'
                else:
                    m = re.search(r'^<a\b.*?href=\"([^\"]+)\"[^>]*><img\b.*?src=\"([^\"]+)\"[^>]*></a>(.*)$', content['text'].strip())
                    if m:
                        item['content_html'] += utils.add_image(m.group(2), link=m.group(1))
                        if m.group(3):
                            item['content_html'] += '<p>' + m.group(3) + '</p>'
                    else:
                        item['content_html'] += '<p>' + content['text'] + '</p>'
        elif content['type'] == 'img':
            item['content_html'] += utils.add_image(content['href'], content.get('text'))
        elif content['type'] == 'photo_gallery':
            if len(content['data']) == 1:
                item['content_html'] += utils.add_image(content['data'][0]['original'], content['data'][0].get('caption'))
            else:
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                for img in content['data']:
                    item['content_html'] += '<div style="flex:1; min-width:200px;">{}</div>'.format(utils.add_image(img['original'], img.get('caption')))
                item['content_html'] += '</div>'
                if content.get('sectionTitle'):
                    item['content_html'] += '<div style="margin-top:4px;"><small>{}</small></div>'.format(content['sectionTitle'])
        elif content['type'] == 'video' and content.get('href'):
            m = re.search(r'<iframe\b.*?src=\"([^\"]+)\"', content['href'])
            if m:
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled video in ' + item['url'])
        elif content['type'] == 'related_posts':
            continue
        else:
            logger.warning('unhandled content type {} in {}'.format(content['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.theepochtimes.com/rssfeeds
    return rss.get_feed(url, args, site_json, save_debug, get_content)
