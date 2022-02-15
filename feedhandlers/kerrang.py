import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    split_url = urlsplit(img_src)
    return 'https://{}{}?auto=compress&fit=max&w={}'.format(split_url.netloc, split_url.path, width)


def get_next_json(url):
    sites_json = utils.read_json_file('./sites.json')
    next_url = 'https://www.kerrang.com/_next/data/' + sites_json['kerrang']['buildId']

    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path:
        next_url += split_url.path + '.json'
    else:
        next_url += '/index.json'

    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        logger.debug('updating kerrang.com buildId')
        article_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([a-f0-9]+)"', article_html)
        if m:
            sites_json['kerrang']['buildId'] = m.group(1)
            utils.write_file(sites_json, './sites.json')
            next_json = utils.get_url_json(
                'https://www.kerrang.com/_next/data/{}{}.json'.format(m.group(1), split_url.path))
            if not next_json:
                return None
    return next_json


def get_content(url, args, save_debug):
    next_json = get_next_json(url)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    article_json = next_json['pageProps']['entry']
    item = {}
    item['id'] = article_json['id']
    item['url'] = next_json['pageProps']['seo']['canonical']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['lastUpdated']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    # Check age
    if args.get('age'):
        if not utils.check_age(item, args):
            return None

    authors = []
    for it in article_json['byline']:
        if it.get('credit') and 'Photo' in it['credit']:
            continue
        authors.append(it['creditName'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('tags'):
        for it in article_json['tags']:
            item['tags'].append(it['title'])
    if article_json.get('artists'):
        for it in article_json['artists']:
            item['tags'].append(it['title'])
    if not item.get('tags'):
        del item['tags']

    item['summary'] = article_json['summary']

    item['content_html'] = ''
    if article_json['__typename'] == 'entries_feature_Entry':
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['summary'])

    if article_json.get('image'):
        item['_image'] = resize_image(article_json['image'][0]['src'])
        for image in article_json['image']:
            item['content_html'] += utils.add_image(resize_image(image['src']))

    for block in article_json['contentBlocks']:
        if block['__typename'] == 'contentBlocks_textBlock_BlockType':
            #if block.get('addDropcaps'):
            #    text =
            item['content_html'] += block['text']

        elif block['__typename'] == 'contentBlocks_videoBlock_BlockType':
            if 'youtube.com' in block['video'] or 'youtu.be' in block['video']:
                item['content_html'] += utils.add_embed(block['video'])
            else:
                logger.warning('unhandled video {} in {}'.format(block['video'], url))

        elif block['__typename'] == 'contentBlocks_imageBlock_BlockType':
            for image in block['image']:
                item['content_html'] += utils.add_image(resize_image(image['src']))

        elif block['__typename'] == 'contentBlocks_heading_BlockType':
            item['content_html'] += '<center><h3>'
            if block.get('headingPrefix'):
                item['content_html'] += '<span style="font-size:1.2em; text-decoration:underline;">{}</span><br/>'.format(block['headingPrefix'])
            item['content_html'] += '<span>{}</span></h3></center>'.format(block['text'])

        elif block['__typename'] == 'contentBlocks_tweetBlock_BlockType':
            item['content_html'] += utils.add_embed(block['tweet'])

        elif block['__typename'] == 'contentBlocks_instagramBlock_BlockType':
            m = re.search(r'data-instgrm-permalink="([^"\?]+)', block['embedCode'])
            if m:
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unable to determine Instagram url in ' + url)

        elif block['__typename'] == 'contentBlocks_htmlBlock_BlockType':
            if '<iframe' in block['html']:
                m = re.search(r'src="([^"\?]+)', block['html'])
                if m:
                    item['content_html'] += utils.add_embed(m.group(1))
            elif 'instagram.com' in block['html']:
                m = re.search(r'data-instgrm-permalink="([^"\?]+)', block['html'])
                if m:
                    item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled to htmlBlock in ' + url)

        elif block['__typename'] == 'contentBlocks_spotifyBlock_BlockType':
            m = re.search(r'src="([^"\?]+)', block['embedCode'])
            if m:
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unable to determine Spotify url in ' + url)


        elif block['__typename'] == 'contentBlocks_pullquoteBlock_BlockType':
            if block.get('attribution'):
                item['content_html'] += utils.add_pullquote(block['quote'], block['attribution'])
            else:
                item['content_html'] += utils.add_pullquote(block['quote'])

        elif block['__typename'] == 'contentBlocks_audioQuote_BlockType':
            item['content_html'] += utils.add_pullquote(block['quote'])
            item['content_html'] += '<div style="margin-bottom:1em;"><a href="{}"><img style="float:left; margin-right:8px;" src="{}/static/play_button-48x48.png"/></a><div style="overflow:hidden;"><h5 style="margin-top:0; margin-bottom:0;">{}</h5></div><div style="clear:left;"></div></div>'.format(block['file'][0]['src'], config.server, block['subText'])

        elif block['__typename'] == 'contentBlocks_adUnitBlock_BlockType':
            pass

        else:
            logger.warning('unhandled contentBlock type {} in {}'.format(block['__typename'], url))

    return item

def get_feed(args, save_debug=False):
    # https://www.kerrang.com/feed.rss
    if 'feed.rss' in args['url']:
        return rss.get_feed(args, save_debug, get_content)

    next_json = get_next_json(args['url'])
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')

    if next_json['pageProps'].get('entries'):
        articles = next_json['pageProps']['entries']
    elif next_json['pageProps'].get('latest'):
        articles = next_json['pageProps']['latest']
    else:
        logger.warning('unknown article list in ' + args['url'])
        return None

    n = 0
    items = []
    for article in articles:
        url = 'https://www.kerrang.com/' + article['slug']
        if save_debug:
            logger.debug('getting contents for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed
