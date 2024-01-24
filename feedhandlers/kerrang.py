import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    split_url = urlsplit(img_src)
    return 'https://{}{}?auto=compress&fit=max&w={}'.format(split_url.netloc, split_url.path, width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path:
        path += '.json'
        params = '?slug=' + paths[-1]
    else:
        path = '/index.json'
        params = ''
    next_url = 'https://www.kerrang.com/_next/data/{}{}{}'.format(site_json['buildId'], path, params)
    print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    article_json = next_data['pageProps']['entry']
    meta_json = json.loads(article_json['seomatic']['metaJsonLdContainer'])
    if save_debug:
        utils.write_file(meta_json, './debug/meta.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = meta_json['mainEntityOfPage']['url']
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
    else:
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

        elif block['__typename'] == 'contentBlocks_galleryBlock_BlockType':
            for image in block['images']:
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
            elif 'reddit-embed-bq' in block['html']:
                m = re.search(r'href="([^"\?]+)', block['html'])
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

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item

def get_feed(url, args, site_json, save_debug=False):
    # https://www.kerrang.com/feed.rss
    if 'feed.rss' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    if next_data['pageProps'].get('entries'):
        articles = next_data['pageProps']['entries']
    elif next_data['pageProps'].get('latest'):
        articles = next_data['pageProps']['latest']
    else:
        logger.warning('unknown article list in ' + args['url'])
        return None

    n = 0
    items = []
    for article in articles:
        url = 'https://www.kerrang.com/' + article['slug']
        if save_debug:
            logger.debug('getting contents for ' + url)
        item = get_content(url, args, site_json, save_debug)
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
