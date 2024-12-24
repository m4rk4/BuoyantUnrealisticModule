import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import bbcarticle, bbcnews, bbcsport, rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
        params = ''
    else:
        params = '?slug=' + '&slug='.join(paths)
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
    path += '.json'
    next_url = '{}://{}/bbcx/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, params)
    # print(next_url)
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


def get_initial_data(url):
    article_html = utils.get_url_html(url)
    if not article_html:
        return None
    m = re.search(r'window\.__INITIAL_DATA__="(.+?)";<\/script>', article_html)
    if not m:
        logger.warning('unable to find __INITIAL_DATA__ in ' + url)
        return None
    # utils.write_file(m.group(1), './debug/debug.txt')
    data = m.group(1).replace('\\"', '"')
    data = data.replace('\\"', '\"')
    initial_data = json.loads(data)
    return initial_data


def get_video_src(vpid):
    video_src = ''
    caption = ''
    # media_js = utils.get_url_html('https://open.live.bbc.co.uk/mediaselector/6/select/version/2.0/mediaset/pc/vpid/{}/format/json/jsfunc/JS_callbacks0'.format(vpid))
    # if media_js:
    #  media_json = json.loads(media_js[19:-2])
    media_json = utils.get_url_json(
        'https://open.live.bbc.co.uk/mediaselector/6/select/version/2.0/mediaset/pc/vpid/{}/format/json/jsfunc'.format(
            vpid))
    if media_json:
        if media_json.get('media'):
            for media in media_json['media']:
                if media['kind'] == 'video':
                    for connection in media['connection']:
                        if connection['transferFormat'] == 'hls' and connection['protocol'] == 'https':
                            return connection['href'], caption
        elif media_json.get('result'):
            if media_json['result'] == 'geolocation':
                caption = 'This content is not available in your location'
    else:
        logger.warning('unable to get media info for vid ' + vpid)
        caption = 'Unable to get video info'
    return video_src, caption


def get_av_content(url, args, site_json, save_debug=False):
    initial_data = get_initial_data(url)
    if save_debug:
        utils.write_file(initial_data, './debug/debug.json')

    article_json = None
    for key, val in initial_data['data'].items():
        if key.startswith('media-experience'):
            article_json = val
    if not article_json:
        logger.warning('unable to find article content in ' + url)

    item = {}
    item['id'] = article_json['props']['id']
    item['url'] = url
    for it in article_json['data']['initialItem']['pageMetadata']['linkTags']:
        if it['rel'] == 'canonical':
            item['url'] = it['href']
    item['title'] = article_json['data']['initialItem']['structuredData']['name']

    dt = datetime.fromisoformat(article_json['data']['initialItem']['structuredData']['uploadDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": "BBC News"
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    for it in article_json['data']['initialItem']['mediaItem']['metadata']['items']:
        if it['label'] == 'Section' or it['label'] == 'Subsection':
            item['tags'].append(it['text'])
    if not item.get('tags'):
        del item['tags']

    images = []
    for it in article_json['data']['initialItem']['structuredData']['thumbnailUrl']:
        m = re.search(r'\/ic\/(\d+)', it)
        if m:
            images.append({"width": m.group(1), "url": it})
    if images:
        item['image'] = utils.closest_dict(images, 'width', 1000)['url']

    item['summary'] = article_json['data']['initialItem']['structuredData']['description']

    item['content_html'] = ''
    if article_json['data']['initialItem']['mediaItem']['media']['__typename'] == 'ElementsMediaPlayer':
        video_src, caption = get_video_src(article_json['data']['initialItem']['mediaItem']['media']['items'][0]['id'])
        poster = article_json['data']['initialItem']['mediaItem']['media']['items'][0]['holdingImageUrl'].replace(
            '$recipe', '976x549')
        if video_src:
            caption = article_json['data']['initialItem']['mediaItem']['media']['items'][0]['title']
            item['content_html'] += utils.add_video(video_src, 'application/x-mpegURL', poster, caption)
        else:
            poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(poster))
            item['content_html'] += utils.add_image(poster, caption)

    else:
        logger.warning('unhandled media typename {} in {}'.format(
            article_json['data']['initialItem']['mediaItem']['media']['__typename'], url))

    item['content_html'] += bbcnews.format_content(article_json['data']['initialItem']['mediaItem']['summary'])
    return item


def render_contents(content_blocks, body_intro=False, heading=0):
    content_html = ''
    for block in content_blocks:
        if block['type'] == 'headline' or block['type'] == 'timestamp' or block['type'] == 'byline' or block['type'] == 'subByline' or block['type'] == 'advertisement' or block['type'] == 'links':
            continue
        elif block['type'] == 'text':
            content_html += render_contents(block['model']['blocks'], block['model'].get('bodyIntro'), heading)
        elif block['type'] == 'paragraph':
            if heading > 0:
                content_html += '<h{0}>{1}</h{0}>'.format(heading, render_contents(block['model']['blocks']))
            else:
                if body_intro:
                    content_html += '<p style="font-weight:bold;">' + render_contents(block['model']['blocks']) + '</p>'
                else:
                    content_html += '<p>' + render_contents(block['model']['blocks']) + '</p>'
        elif block['type'] == 'fragment':
            start_tag = ''
            end_tag = ''
            if block['model'].get('attributes'):
                for attr in block['model']['attributes']:
                    if attr == 'bold':
                        start_tag += '<b>'
                        end_tag = '</b>' + end_tag
                    elif attr == 'italic':
                        start_tag += '<i>'
                        end_tag = '</i>' + end_tag
                    else:
                        logger.warning('unhandled attribute ' + attr)
            content_html += start_tag + block['model']['text'] + end_tag
        elif block['type'] == 'subheadline':
            content_html += render_contents(block['model']['blocks'], heading=block['model']['level'])
        elif block['type'] == 'urlLink':
            content_html += '<a href="{}">'.format(block['model']['locator'])
            content_html += render_contents(block['model']['blocks']) + '</a>'
        elif block['type'] == 'image':
            image = next((it for it in block['model']['blocks'] if it['type'] == 'rawImage'), None)
            if image:
                if image['model']['originCode'] == 'cpsprodpb':
                    img_src = 'https://ichef.bbci.co.uk/news/1024/cpsprodpb/{}.webp'.format(image['model']['locator'])
                elif image['model']['originCode'] == 'ic':
                    img_src = 'https://ichef.bbci.co.uk/images/ic/1024xn/' + image['model']['locator']
                else:
                    logger.warning('handled image originCode ' + image['model']['originCode'])
                    img_src = image['model']['locator']
                blk = next((it for it in block['model']['blocks'] if it['type'] == 'caption'), None)
                if blk:
                    caption = render_contents(blk['model']['blocks'])
                    caption = re.sub(r'^<p>(.*?)</p>$', r'\1', caption)
                else:
                    caption = ''
                content_html += utils.add_image(img_src, caption)
        elif block['type'] == 'video':
            # https://open.live.bbc.co.uk/mediaselector/6/select/version/2.0/mediaset/pc/vpid/p0h3g3rs/format/json/cors/1
            video_src = ''
            poster = ''
            caption = ''
            blk = next((it for it in block['model']['blocks'] if it['type'] == 'media'), None)
            if blk:
                if blk['model']['blocks'][0]['model']['versions'][0]['availableTerritories']['nonUk'] == True:
                    video_id = blk['model']['blocks'][0]['model']['versions'][0]['versionId']
                    media_url = 'https://open.live.bbc.co.uk/mediaselector/6/select/version/2.0/mediaset/pc/vpid/{}/format/json/cors/1'.format(video_id)
                    # print(media_url)
                    media_json = utils.get_url_json(media_url)
                    if media_json:
                        # utils.write_file(media_json, './debug/video.json')
                        media = next((it for it in media_json['media'] if it['type'] == 'video/mp4'), None)
                        if media:
                            for connection in media['connection']:
                                if connection['transferFormat'] == 'hls' and connection['protocol'] == 'https':
                                    video_src = connection['href']
                                    break
                    poster = blk['model']['blocks'][0]['model']['imageUrl'].replace('$recipe', '1024xn')
                    caption = blk['model']['blocks'][0]['model']['title']
                    if video_src:
                        content_html += utils.add_video(video_src, 'application/x-mpegURL', poster, caption)
                    else:
                        logger.warning('unhandled video content')
                else:
                    poster = blk['model']['blocks'][0]['model']['imageUrl'].replace('$recipe', '1024xn')
                    caption = '<em>Video unavailable</em> | ' + blk['model']['blocks'][0]['model']['title']
                    content_html += utils.add_image(poster, caption)
        elif block['type'] == 'social':
            if block['model']['source'] == 'twitter':
                content_html += utils.add_embed(block['model']['href'])
            else:
                logger.warning('unhandled social content source ' + block['model']['source'])
        elif block['type'] == 'callout':
            quote = ''
            if block['model'].get('title'):
                quote += '<h3>' + block['model']['title'] + '</h3>'
            quote += '<div>' + render_contents(block['model']['blocks']) + '</div>'
            content_html += utils.add_blockquote(quote)
        elif block['type'] == 'include':
            if block['model']['type'] == 'idt2':
                content_html += utils.add_image(block['model']['idt2Image']['src'])
            elif block['model'].get('html'):
                if block['model']['type'] == 'customEmbedded' and block['model']['html'].startswith('<iframe'):
                    m = re.search(r'src="([^"]+)"', block['model']['html'])
                    content_html += utils.add_embed(m.group(1))
                elif re.search(r'hearken-curiosity', block['model']['html']) or block['model']['html'].startswith('</'):
                    continue
                else:
                    logger.warning('unhandled content block type include')
            else:
                logger.warning('unhandled content block type include')
        elif block['type'] == 'unorderedList':
            content_html += '<ul>' + render_contents(block['model']['blocks']) + '</ul>'
        elif block['type'] == 'orderedList':
            content_html += '<ol>' + render_contents(block['model']['blocks']) + '</ol>'
        elif block['type'] == 'listItem':
            content_html += '<li>' + render_contents(block['model']['blocks']) + '</li>'
        elif block['type'] == 'quote':
            content_html += utils.add_pullquote(block['model']['text'], block['model']['quoteSource'])
        elif block['type'] == 'contributor' or block['type'] == 'name' or block['type'] == 'role':
            content_html += render_contents(block['model']['blocks'])
        else:
            logger.warning('unhandled content block type ' + block['type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    page_json = next_data['pageProps']['page'][next_data['pageProps']['pageKey']]
    metadata = next_data['pageProps']['metadata']

    item = {}
    item['id'] = next_data['pageProps']['analytics']['contentId']
    item['url'] = utils.clean_url(url)
    item['title'] = metadata['seoHeadline']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(metadata['firstPublished'] / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if metadata.get('lastUpdated'):
        dt_loc = datetime.fromtimestamp(metadata['lastUpdated'] / 1000)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if metadata.get('contributor'):
        item['author']['name'] = re.sub(r'^By ', '', metadata['contributor'])
    else:
        block = None
        if page_json.get('headerContents'):
            block = next((it for it in page_json['headerContents'] if it['type'] == 'byline'), None)
        if not block:
            block = next((it for it in page_json['contents'] if it['type'] == 'byline'), None)
        if block:
            byline = render_contents(block['model']['blocks'])
            m = re.search(r'By ([^<]+)', byline)
            if m:
                item['author']['name'] = m.group(1)
            else:
                m = re.search(r'<p>(.*?)</p>', byline)
                if m:
                    item['author']['name'] = m.group(1)
    if 'name' not in item['author']:
        item['author']['name'] = 'BBC'

    if metadata.get('indexImage'):
        item['image'] = metadata['indexImage']['originalSrc']
    elif page_json.get('headerContents'):
        if page_json['contents'][0]['type'] == 'image' or page_json['contents'][0]['type'] == 'video':
            block = page_json['contents'][0]
        else:
            block = next((it for it in page_json['headerContents'] if it['type'] == 'image'), None)
        if block:
            image = render_contents([block])
            m = re.search(r'src="([^"]+)"', image)
            if m:
                item['image'] = m.group(1)

    if metadata.get('description'):
        item['summary'] = metadata['description']
    else:
        for block in page_json['contents']:
            if block['type'] == 'text':
                break
        if block['type'] == 'text':
            text = render_contents([block])
            m = re.search(r'<p>(.*?)</p>', text)
            if m:
                item['summary'] = m.group(1)

    item['tags'] = []
    if page_json.get('section'):
        for it in page_json['section']:
            if it['title'] not in item['tags']:
                item['tags'].append(it['title'])
    if page_json.get('pillar'):
        for it in page_json['pillar']:
            if it['title'] not in item['tags']:
                item['tags'].append(it['title'])
    if page_json.get('topics'):
        for it in page_json['topics']:
            if it['title'] not in item['tags']:
                item['tags'].append(it['title'])

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    if page_json.get('headerContents'):
        item['content_html'] += render_contents(page_json['headerContents'])

    item['content_html'] += render_contents(page_json['contents'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])

    if next_data['pageProps']['type'] == 'video':
        m = re.search(r'Video by ([^\.<]+)', item['content_html'])
        if m:
            item['author']['name'] = m.group(1)
    item['authors'] = []
    item['authors'].append(item['author'])

    return item

    # if '/av/' in url:
    #     return get_av_content(url, args, site_json, save_debug)
    # elif '/article/' in url:
    #     return bbcarticle.get_content(url, args, site_json, save_debug)
    # elif '/news/' in url:
    #     return bbcnews.get_content(url, args, site_json, save_debug)
    # elif '/sport/' in url:
    #     return bbcsport.get_content(url, args, site_json, save_debug)
    # else:
    #     logger.warning('unknown BBC handler for ' + url)
    #     return None


def get_feed(url, args, site_json, save_debug=False):
    # RSS feeds: https://www.bbc.co.uk/news/10628494
    if 'rss.xml' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    else:
        return bbcarticle.get_feed(url, args, site_json, save_debug)
