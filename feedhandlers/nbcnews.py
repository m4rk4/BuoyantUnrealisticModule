import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    return img_src.replace('image/upload/', 'image/upload/t_fit-{}w,f_auto,q_auto:best/'.format(width))


def add_image(image):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('source'):
        captions.append(image['source']['name'])
    return utils.add_image(resize_image(image['url']['primary']), ' | '.join(captions))


def add_video(video):
    video_assets = []
    for video_asset in video['videoAssets']:
        if video_asset['format'] == 'MPEG4':
            video_assets.append(video_asset)
    video_asset = utils.closest_dict(video_assets, 'height', 480)

    video_html = utils.get_url_html(video_asset['publicUrl'])
    video_soup = BeautifulSoup(video_html, 'html.parser')
    video_assets = []
    videos = video_soup.find_all('video')
    if videos:
        for el in videos:
            video_asset = {}
            video_asset['src'] = el['src']
            video_asset['height'] = el['height']
            video_asset['width'] = el['width']
            video_assets.append(video_asset)
        video_asset = utils.closest_dict(video_assets, 'height', 480)
        video_src = video_asset['src']
        poster = resize_image(video['primaryImage']['url']['primary'])
        captions = []
        if video.get('headline'):
            captions.append(video['headline']['primary'])
        if video.get('source'):
            captions.append(video['source']['name'])
    else:
        el = video_soup.find('ref')
        if el:
            video_src = el['src']
            poster = '{}/image?width=960&height=540&color=grey&overlay=videeo'.format(config.server)
            captions = []
            if el.has_attr('title'):
                captions.append(el['title'])
            if el.has_attr('abstract'):
                captions.append(el['abstract'])
        else:
            return ''
    return utils.add_video(video_src, 'video/mp4', poster, ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    article_html = utils.get_url_html(url)
    article_soup = BeautifulSoup(article_html, 'html.parser')
    next_data = article_soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return None
    next_json = json.loads(next_data.string)
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    if next_json['page'] == '/article':
        article_json = next_json['props']['initialState']['article']['content'][0]
    elif next_json['page'] == '/video' or next_json['page'] == '/videoEmbed':
        article_json = next_json['props']['initialState']['video']['current']
    elif next_json['page'] == '/slideshow':
        article_json = next_json['props']['initialState']['slideshow']['current']
    else:
        logger.warning('unknown page type {} in {}'.format(next_json['page'], url))
        return None

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']['canonical']
    item['title'] = article_json['headline']['primary']

    if article_json.get('date'):
        dt_pub = datetime.fromisoformat(article_json['date']['publishedAt'].replace('Z', '+00:00'))
        dt_mod = datetime.fromisoformat(article_json['date']['modifiedAt'].replace('Z', '+00:00'))
    else:
        dt_pub = datetime.strptime(article_json['datePublished'], '%a %b %d %Y %H:%M:%S GMT+0000 (UTC)').astimezone(
            timezone.utc)
        dt_mod = datetime.strptime(article_json['dateModified'], '%a %b %d %Y %H:%M:%S GMT+0000 (UTC)').astimezone(
            timezone.utc)
    item['date_published'] = dt_pub.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = utils.format_display_date(dt_pub)
    item['date_modified'] = dt_mod.isoformat()

    if article_json.get('authors'):
        authors = []
        for author in article_json['authors']:
            authors.append(author['person']['name'].strip())
        if authors:
            item['author'] = {}
            if len(authors) == 1:
                item['author']['name'] = authors[0]
            else:
                item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('source'):
        item['author'] = {}
        item['author']['name'] = article_json['source']['name']

    item['tags'] = []
    for key, val in article_json['taxonomy'].items():
        if isinstance(article_json['taxonomy'][key], dict):
            if not article_json['taxonomy'][key]['name'] in item['tags']:
                item['tags'].append(article_json['taxonomy'][key]['name'])
        elif isinstance(article_json['taxonomy'][key], list):
            for tag in article_json['taxonomy'][key]:
                if not tag['name'] in item['tags']:
                    item['tags'].append(tag['name'])

    item['content_html'] = ''
    if article_json.get('dek'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['dek'])

    if article_json.get('primaryMedia'):
        if article_json['primaryMedia'].get('video'):
            item['content_html'] += add_video(article_json['primaryMedia']['video'])
            item['_image'] = resize_image(article_json['primaryMedia']['video']['primaryImage']['url']['primary'])
        elif article_json['primaryMedia'].get('image'):
            item['content_html'] += add_image(article_json['primaryMedia']['image'])
            item['_image'] = resize_image(article_json['primaryMedia']['image']['url']['primary'])
    elif article_json.get('primaryImage'):
        item['_image'] = resize_image(article_json['primaryImage']['url']['primary'])

    item['summary'] = article_json['description']['primary']

    if article_json.get('videoAssets'):
        item['content_html'] += add_video(article_json)
        if not 'embed' in args:
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    if article_json.get('slides'):
        for slide in article_json['slides']:
            img_src = resize_image(slide['image']['url']['primary'])
            captions = []
            if slide['image'].get('caption'):
                captions.append(slide['image']['caption'])
            if slide['image'].get('authors'):
                authors = []
                for author in slide['authors']:
                    authors.append(author['name'])
                captions.append(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
            if slide['image'].get('source'):
                captions.append(slide['source']['name'])
            if slide['headline'].get('primary'):
                item['content_html'] += '<h4>{}</h4>'.format(slide['headline']['primary'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

    if article_json.get('body'):
        for el in article_json['body']:
            if el['type'] == 'markup':
                if el['element'] == 'br':
                    item['content_html'] += '<{}/>'.format(el['element'])
                elif el['element'] == 'blockquote':
                    if el['html'].startswith('<p>"') and el['html'].endswith('"</p>'):
                        item['content_html'] += utils.add_pullquote(el['html'])
                    else:
                        item['content_html'] += utils.add_blockquote(el['html'])
                else:
                    item['content_html'] += '<{0}>{1}</{0}>'.format(el['element'], el['html'])

            elif el['type'] == 'embeddedImage':
                item['content_html'] += add_image(el['image'])

            elif el['type'] == 'embeddedVideo':
                if el.get('video'):
                    item['content_html'] += add_video(el['video'])

            elif el['type'] == 'embeddedWidget':
                widget_html = ''
                if el['widget']['name'] == 'CUSTOM_EMBED':
                    if el['widget']['properties']['embed']['type'] == 'BLOCKQUOTE':
                        widget_html = utils.add_blockquote(el['widget']['properties']['embed']['text'].strip())

                    elif el['widget']['properties']['embed']['type'] == 'PULL_QUOTE':
                        widget_html = utils.add_pullquote(el['widget']['properties']['embed']['text'].strip(),
                                                          el['widget']['properties']['embed']['attribution'])

                    elif el['widget']['properties']['embed']['type'] == 'LIFT_OUT':
                        widget_html = 'pass'

                elif el['widget']['name'] == 'nbc_blockquote':
                    embed_soup = BeautifulSoup(unquote_plus(el['widget']['baseline']), 'html.parser')
                    widget_html = utils.add_blockquote(embed_soup.get_text())

                elif el['widget']['name'] == 'youtubeplus':
                    embed_soup = BeautifulSoup(unquote_plus(el['widget']['baseline']), 'html.parser')
                    widget_html = utils.add_embed(embed_soup.iframe['src'])

                elif el['widget']['name'] == 'tweetplus_embed':
                    embed_soup = BeautifulSoup(unquote_plus(el['widget']['baseline']), 'html.parser')
                    tweet_url = embed_soup.find_all('a')[-1]['href']
                    if re.search(r'https:\/\/twitter\.com/[^\/]+\/status\/\d+', tweet_url):
                        widget_html = utils.add_embed(tweet_url)

                elif el['widget']['name'] == 'instagramplus':
                    widget_html = utils.add_embed(el['widget']['fallbackUrl'])

                elif el['widget']['name'] == 'IFRAMELY_EXTERNAL_EMBED':
                    embed_soup = BeautifulSoup(unquote_plus(el['widget']['baseline']), 'html.parser')
                    if embed_soup.div and embed_soup.div.has_attr('class'):
                        if 'iframely-twitter' in embed_soup.div['class']:
                            widget_html = utils.add_embed(el['widget']['fallbackUrl'])
                        elif 'iframely-youtube' in embed_soup.div['class']:
                            widget_html = utils.add_embed(el['widget']['fallbackUrl'])
                        elif 'iframely-card' in embed_soup.div['class']:
                            if re.search('^https:\/\/www\.(msnbc|nbcnews)\.com', el['widget']['fallbackUrl']):
                                widget_html = 'pass'
                        else:
                            widget_html = '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(
                                el['widget']['fallbackUrl'])

                elif el['widget']['name'] == 'advanced_embed':
                    embed_html = unquote_plus(el['widget']['baseline'])
                    m = re.search(r'https:\/\/dataviz\.nbcnews\.com\/projects\/[^\/]+\/[^\.]+\.html', embed_html)
                    if m:
                        widget_html = '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(
                            m.group(0))
                    elif re.search(r'opinary-widget-embed|menu-embed', embed_html):
                        widget_html = 'pass'
                    else:
                        embed_soup = BeautifulSoup(embed_html, 'html.parser')
                        if embed_soup.iframe:
                            widget_html = utils.add_embed(embed_soup.iframe['src'])
                        elif embed_soup.blockquote:
                            if 'twitter-tweet' in embed_soup.blockquote['class']:
                                tweet_url = embed_soup.find_all('a')[-1]['href']
                                if re.search(r'https:\/\/twitter\.com/[^\/]+\/status\/\d+', tweet_url):
                                    widget_html = utils.add_embed(tweet_url)

                elif re.search(r'nbc_featuredlink|nbc_liftout', el['widget']['name']):
                    widget_html = 'pass'

                if widget_html != 'pass':
                    if widget_html:
                        item['content_html'] += widget_html
                    else:
                        logger.warning('unhandled embeddedWidget in ' + url)

            elif el['type'] == 'embeddedProduct':
                poster = '{}/image?height=128&url={}'.format(config.server,
                                                             el['product']['teaseImage']['url']['primary'])
                desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4>${} at <a href="{}">{}</a>'.format(
                    utils.get_redirect_url(el['product']['offers'][0]['externalUrl']), el['product']['name'],
                    el['product']['offers'][0]['price'], el['product']['offers'][0]['seller']['externalUrl'],
                    el['product']['offers'][0]['seller']['name'])
                item[
                    'content_html'] += '<div><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;">&nbsp;</div>'.format(
                    poster, desc)

            else:
                logger.warning('unhandled body type {} in {}'.format(el['type'], url))

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    article_html = utils.get_url_html(args['url'])
    article_soup = BeautifulSoup(article_html, 'html.parser')
    next_data = article_soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return None
    next_json = json.loads(next_data.string)
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')

    all_items = []
    for layout in next_json['props']['initialState']['front']['curation']['layouts']:
        for package in layout['packages']:
            for item in package['items']:
                if item['type'] == 'custom':
                    logger.warning('skipping custom item ' + item['computedValues']['url'])
                    continue
                it = {}
                it['id'] = item['id']
                it['url'] = item['computedValues']['url']
                dt = datetime.strptime(item['item']['datePublished'], '%a %b %d %Y %H:%M:%S GMT+0000 (UTC)').astimezone(
                    timezone.utc)
                it['_timestamp'] = dt.timestamp()
                if 'age' in args:
                    if not utils.check_age(it, args):
                        continue
                all_items.append(it)

    uniq_items = {it['id']: it for it in all_items}.values()
    sorted_items = sorted(uniq_items, key=lambda i: i['_timestamp'], reverse=True)

    n = 0
    items = []
    for it in sorted_items:
        if save_debug:
            logger.debug('getting content for ' + it['url'])
        if split_url.netloc in it['url']:
            item = get_content(it['url'], args, site_json, save_debug)
        elif '3rd_party' in args:
            item = utils.get_content(it['url'], args, site_json, save_debug)
        else:
            continue
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
