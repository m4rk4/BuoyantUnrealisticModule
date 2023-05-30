import json, math, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from markdown2 import markdown
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_image(image, gallery=None, width=1000):
    img_src = 'https://cdn.apollo.audio/{}/{}?quality=80&format=jpg&width={}'.format(image['image']['path'], image['image']['name'], width)
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credits'):
        captions.append(image['credits'])
    desc = ''
    if gallery:
        if image.get('titleText'):
            desc += '<h4>{}</h4>'.format(image['titleText'])
        if image.get('description'):
            desc += '<p>{}</p>'.format(image['description'])
    return utils.add_image(img_src, ' | '.join(captions), desc=desc)


def get_player_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    m = re.search(r'<script>\s*window.__PRELOADED_STATE__\s?=\s?({.*?})\s*</script>', page_html)
    if not m:
        logger.warning('unable to oad PRELOADED_STATE in ' + url)
        return None
    preload_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(preload_json, './debug/debug.json')

    player_json = preload_json['player']['nowPlaying']
    item = {}
    item['id'] = player_json['episodeid']
    item['url'] = player_json['smartlink']
    item['title'] = player_json['title']

    dt = datetime.fromisoformat(player_json['starttime']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    # TODO: lookup showid info
    item['author'] = {"name": paths[0].replace('-', ' ').title()}

    item['_image'] = player_json['imageurl_square']
    poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(item['_image']))

    item['_audio'] = player_json['mediaurl_mp3']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    item['summary'] = player_json['shortdesc']

    duration = []
    s = int(player_json['duration'])
    if s > 3600:
        h = s / 3600
        duration.append('{} hr'.format(math.floor(h)))
        m = (s % 3600) / 60
        if m > 0:
            duration.append('{} min'.format(math.ceil(m)))
    else:
        m = s / 60
        duration.append('{} min'.format(math.ceil(m)))

    item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/><small>{}</small><br/><small>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(item['_audio'], poster, item['url'], item['title'], item['author']['name'], item['_display_date'], ', '.join(duration))
    if 'embed' not in args:
        item['content_html'] += utils.add_blockquote(item['summary'])
    return item

def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[1] == 'player':
        return get_player_content(url, args, site_json, save_debug)

    api_url = 'https://api.publish.apollo.audio/one/articles/?filter=%7B%22publications.furl%22:%22{}%22,%22hiddenArticle%22:false,%22categories.parent.furl%22:%22{}%22,%22published.state%22:%22published%22,%22urls%22:%7B%22$regex%22:%22{}%22%7D,%22categories.furl%22:%22{}%22%7D&page=1&count=5&sort=%7B%22publicationDate%22:-1%7D'.format(paths[0], paths[1], paths[-1], paths[2])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    if len(api_json['results']) == 0:
        logger.warning('unable to find article for ' + url)
        return None

    article_json = None
    for it in api_json['results']:
        if it['furl'] == paths[-1]:
            article_json = it
            break
    if not article_json:
        logger.warning('unable to find article for ' + url)
        return None
    return get_item(article_json, url, args, site_json, save_debug)


def get_item(article_json, url, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['_id']
    item['url'] = url
    item['title'] = article_json['title']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(article_json['_createdAt']/1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('_lastModifiedAt'):
        dt_loc = datetime.fromtimestamp(article_json['_lastModifiedAt']/1000)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

    if article_json.get('author'):
        item['author'] = {"name": article_json['author']['fullname']}
    elif article_json.get('author_custom'):
        item['author'] = {"name": article_json['author_custom']}

    if article_json.get('tags'):
        item['tags'] = []
        for it in article_json['tags']:
            item['tags'].append(it['tag']['name'])

    if article_json.get('heroImage'):
        # https://cdn.apollo.audio/one/media/630f/1ecd/59c6/0664/7360/0c02/foo-fighters-danny-clinch.jpg?quality=80&format=jpg&crop=97,0,660,999&resize=crop
        item['_image'] = 'https://cdn.apollo.audio/{}/{}'.format(article_json['heroImage'][0]['image']['path'], article_json['heroImage'][0]['image']['name'])

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']

    item['content_html'] = ''
    if 'gallery' in args:
        block = next((it for it in article_json['_layout'] if it['type'] == 'imageGalleries'), None)
        if block:
            item['id'] = block['content']['_id']
            item['title'] = block['content']['title']
            for image in block['content']['images']:
                item['content_html'] += add_image(image, True)
            return item

    for block in article_json['_layout']:
        if block['type'] == 'title' or block['type'] == 'tags':
            continue
        elif block['type'] == 'subtitle':
            item['content_html'] += '<p><em>{}</em></p>'.format(block['content'])
        elif block['type'] == 'heroImage' or block['type'] == 'images':
            item['content_html'] += add_image(block['content'])
        elif block['type'] == 'content':
            if block['name'] == 'body':
                content = re.sub(r'{:target=[^}]+}', '', block['content'])
                item['content_html'] += '<p>{}</p>'.format(markdown(content))
        elif block['type'] == 'embeds':
            item['content_html'] += utils.add_embed(block['content']['url'])
        elif block['type'] == 'imageGalleries':
            img_src = 'https://cdn.apollo.audio/{}/{}'.format(block['content']['images'][0]['image']['path'], block['content']['images'][0]['image']['name'])
            link = '{}/content?read&gallery&url={}'.format(config.server, quote_plus(item['url']))
            caption = 'View gallery: <a href="{}">{}</a>'.format(link, block['content']['title'])
            item['content_html'] += utils.add_image(img_src, caption, link=link)
        else:
            logger.warning('unhandled content block type {} in {}'.format(block['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = split_url.path[1:]
    if slug.endswith('/'):
        slug = slug[:-1]
    if len(paths) == 2:
        api_url = 'https://api.publish.apollo.audio/one/articles/?filter=%7B%22publications.furl%22:%22{0}%22,%22hiddenArticle%22:false,%22categories.parent.furl%22:%22{1}%22,%22published.state%22:%22published%22,%22urls%22:%7B%22$regex%22:%22{0}%2F{1}%22%7D%7D&page=1&count=10&sort=%7B%22publicationDate%22:-1%7D'.format(paths[0], paths[1])
        feed_title = '{} | {} | {}'.format(paths[1].replace('-', ' ').title(), paths[0].replace('-', ' ').title(), split_url.netloc)
    elif len(paths) == 3:
        if paths[1] == 'tags':
            api_url = 'https://api.publish.apollo.audio/one/articles/?filter=%7B%22publications.furl%22:%22{}%22,%22hiddenArticle%22:false,%22published.state%22:%22published%22,%22tags.furl%22:%22{}%22%7D&page=1&count=10&sort=%7B%22publicationDate%22:-1%7D'.format(paths[0], paths[2])
        else:
            api_url = 'https://api.publish.apollo.audio/one/articles/?filter=%7B%22publications.furl%22:%22{0}%22,%22hiddenArticle%22:false,%22categories.parent.furl%22:%22{1}%22,%22published.state%22:%22published%22,%22urls%22:%7B%22$regex%22:%22{0}%2F{1}%2F{2}%22%7D,%22categories.furl%22:%22{2}%22%7D&page=1&count=10&sort=%7B%22publicationDate%22:-1%7D'.format(paths[0], paths[1], paths[2])
        feed_title = '{} | {} | {}'.format(paths[2].replace('-', ' ').title(), paths[0].replace('-', ' ').title(), split_url.netloc)
    else:
        logger.warning('unhandled feed url ' + url)
        return None

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in api_json['results']:
        article_url = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, article['urls'][0])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_item(article, article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed