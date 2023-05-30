import json, math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    query = parse_qs(split_url.query)
    if query.get('cropH') and query.get('cropW'):
        crop_w = int(query['cropW'][0])
        crop_h = int(query['cropH'][0])
        if width < crop_w:
            w = width
            h = math.ceil(crop_h * width / crop_w)
        else:
            w = crop_w
            h = crop_h
        img_src = '{}://{}{}?impolicy=wcms_crop_resize&cropW={}&cropH={}&xPos=0&yPos=0&width={}&height={}'.format(split_url.scheme, split_url.netloc, split_url.path, crop_w, crop_h, w, h)
    return img_src


def add_image(image_props, width=1000):
    # TODO: resize
    captions = []
    if image_props.get('caption'):
        captions.append(image_props['caption'])
    if image_props.get('attribution'):
        attrib = format_block(image_props['attribution']['descriptor'])
        captions.append(BeautifulSoup(attrib, 'html.parser').get_text())
    return utils.add_image(resize_image(image_props['imgSrc']), ' | '.join(captions))


def add_video(video_props):
    if len(video_props['document']['media']['video']['renditions']['files']) == 1:
        video = video_props['document']['media']['video']['renditions']['files'][0]
    else:
        videos = []
        for video in video_props['document']['media']['video']['renditions']['files']:
            if video.get('bitRate'):
                videos.append(video)
        video = utils.closest_dict(videos, 'bitRate', 2000)
    caption = 'Video: <a href="{}">{}</a>'.format(video_props['document']['canonicalURL'], video_props['document']['title'])
    if video_props['document']['media'].get('thumbnailLink'):
        # TODO: verify
        poster = resize_image(video_props['document']['media']['thumbnailLink']['cropInfo'][0]['value'][0]['url'])
    else:
        poster = ''
    return utils.add_video(video['url'], video['MIMEType'], poster, caption)


def get_next_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    #utils.write_file(el.string, './debug/debug.txt')
    return json.loads(el.string)


def format_block(block):
    start_tag = ''
    end_tag = ''
    if block['type'] == 'text':
        return block['content']
    if block['type'] == 'tagname':
        if block['key'].startswith('@@'):
            if block['key'] == '@@standfirst':
                start_tag = '<p>'
                end_tag = '</p>'
            elif block['key'] == '@@embed-link':
                start_tag = '<a href="{}">'.format(block['props']['to'])
                end_tag = '</a>'
            elif block['key'] == '@@embed-keypoints':
                start_tag = '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;"><h3>Key points</h3><ul>'
                end_tag = '</ul></blockquote>'
        elif block.get('props'):
            start_tag = '<{}'.format(block['key'])
            for key, val in block['props'].items():
                start_tag += ' {}="{}"'.format(key, val)
            start_tag += '>'
            end_tag = '</{}>'.format(block['key'])
        else:
            start_tag = '<{}>'.format(block['key'])
            end_tag = '</{}>'.format(block['key'])
    elif block['type'] == 'embed':
        if block['key'] == 'Image' or block['key'] == 'ImageProxy':
            return add_image(block['props'])
        elif block['key'] == 'Video':
            return add_video(block['props'])
        elif block['key'] == '@@DataWrapper':
            return utils.add_embed(block['props']['embedURL'])
        elif block['key'] == '@@Iframe':
            if block['props'].get('title') and re.search(r'newsletter', block['props']['title'], flags=re.I):
                return ''
            logger.warning('unhandled embed block key @@Iframe')
        elif block['key'] == 'Teaser':
            start_tag = '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">'
            end_tag = '</blockquote>'
        elif block['key'] == 'Article':
            # Related articles
            return ''
        elif block['key'] == 'ExternalLink':
            if block['props'].get('viewType') and block['props']['viewType'] == 'relatedstory':
                return ''
            logger.warning('unhandled embed block key ExternalLink')
        else:
            logger.warning('unhandled embed block key ' + block['key'])
    elif block['type'] == 'interactive':
        if block['key'] == 'singleTweet' or block['key'] == 'youtube':
            return utils.add_embed(block['props']['embedURL'])
        else:
            logger.warning('unhandled interactive block key ' + block['key'])
    else:
        logger.warning('unhandled block type ' + block['type'])

    block_html = start_tag
    for child in block['children']:
        block_html += format_block(child)
    block_html += end_tag
    return block_html


def get_content(url, args, site_json, save_debug):
    next_data = get_next_data(url)
    if not next_data:
        return None
    #utils.write_file(next_data, './debug/debug.json')

    if next_data['props']['pageProps'].get('productName') and next_data['props']['pageProps']['productName'] == 'radio':
        article_json = next_data['props']['pageProps']['data']['documentProps']
    elif next_data['props']['pageProps']['document']['docType'] == 'Video':
        article_json = next_data['props']['pageProps']['document']['loaders']['media']
    else:
        article_json = next_data['props']['pageProps']['document']['loaders']['articledetail']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['canonicalURL']
    item['title'] = article_json['title']

    if article_json.get('datelinePrepared'):
        if article_json['datelinePrepared'].get('publishedDate'):
            dt = datetime.fromisoformat(article_json['datelinePrepared']['publishedDate']).astimezone(timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
        if article_json['datelinePrepared'].get('updatedDate'):
            dt = datetime.fromisoformat(article_json['datelinePrepared']['updatedDate']).astimezone(timezone.utc)
            item['date_modified'] = dt.isoformat()
    elif article_json.get('headlinePrepared'):
        if article_json['headlinePrepared'].get('firstUpdated'):
            dt = datetime.fromisoformat(article_json['headlinePrepared']['firstUpdated']).astimezone(timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
        if article_json['headlinePrepared'].get('lastUpdated'):
            dt = datetime.fromisoformat(article_json['headlinePrepared']['lastUpdated']).astimezone(timezone.utc)
            item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    if article_json['docType'] == 'audio':
        item['author']['name'] = article_json['analytics']['document']['program']['name']
    elif article_json.get('headlinePrepared'):
        if article_json['headlinePrepared'].get('newsBylinePrepared'):
            if article_json['headlinePrepared']['newsBylinePrepared'].get('byline'):
                byline = format_block(article_json['headlinePrepared']['newsBylinePrepared']['byline']['descriptor'])
                if byline:
                    authors.append(BeautifulSoup(byline, 'html.parser').get_text())
            if article_json['headlinePrepared']['newsBylinePrepared'].get('authors'):
                for it in article_json['headlinePrepared']['newsBylinePrepared']['authors']:
                    if it['name'] not in authors:
                        authors.append(it['name'])
        elif article_json['headlinePrepared'].get('byline'):
            logger.warning('unhandled headlinePrepared byline')
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'ABC News'

    if article_json['headTagsPagePrepared'].get('keywords'):
        item['tags'] = article_json['headTagsPagePrepared']['keywords'].copy()

    if article_json.get('synopsis'):
        item['summary'] = article_json['synopsis']

    if article_json.get('headTagsArticlePrepared') and article_json['headTagsArticlePrepared'].get('schema') and article_json['headTagsArticlePrepared']['schema'].get('image'):
        item['_image'] = resize_image(article_json['headTagsArticlePrepared']['schema']['image']['url'])

    item['content_html'] = ''
    if article_json['docType'] == 'video':
        video = utils.closest_dict(article_json['headlinePrepared']['media']['renditions'], 'height', 480)
        if article_json['headlinePrepared']['media'].get('thumbnailLink'):
            poster = resize_image(article_json['headlinePrepared']['media']['thumbnailLink']['cropInfo'][0]['value'][0]['url'])
            item['_image'] = poster
        else:
            poster = ''
        caption = 'Video: <a href="{}">{}</a>'.format(item['url'], item['title'])
        if article_json['headlinePrepared']['media'].get('caption'):
            caption += ' | ' + article_json['headlinePrepared']['media']['caption']['plain']
        item['content_html'] += utils.add_video(video['url'], video['contentType'], poster, caption)
    if article_json['docType'] == 'audio':
        captions = []
        if article_json.get('thumbnailLink') and article_json['thumbnailLink'].get('picture'):
            item['_image'] = resize_image(article_json['thumbnailLink']['picture']['cropInfo'][0]['value'][0]['url'])
            if article_json['thumbnailLink'].get('caption'):
                captions.append(article_json['thumbnailLink']['caption']['plain'])
            if article_json['thumbnailLink'].get('byline'):
                captions.append(article_json['thumbnailLink']['byline']['plain'])
        elif article_json.get('embedded') and article_json['embedded'].get('mediaThumbnail'):
            item['_image'] = resize_image(article_json['embedded']['mediaThumbnail']['cropInfo'][0]['value'][0]['url'])
            if article_json['embedded']['mediaThumbnail'].get('caption'):
                captions.append(article_json['embedded']['mediaThumbnail']['caption']['plain'])
            if article_json['embedded']['mediaThumbnail'].get('byline'):
                captions.append(article_json['embedded']['mediaThumbnail']['byline']['plain'])
        duration = []
        s = article_json['duration']
        if s > 3600:
            h = s / 3600
            duration.append('{} hr'.format(math.floor(h)))
            m = (s % 3600) / 60
            duration.append('{} min'.format(math.ceil(m)))
        else:
            m = s / 60
            duration.append('{} min'.format(math.ceil(m)))
        captions.insert(0, '<a href="{}">Listen ({})</a>'.format(item['url'], ', '.join(duration)))
        poster = '{}/image?url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
        item['content_html'] += utils.add_image(poster, ' | '.join(captions), link=article_json['renditions'][0]['url'])
    elif article_json.get('featureMediaPrepared') and article_json['featureMediaPrepared'].get('heroContent'):
        if article_json['featureMediaPrepared']['heroContent']['descriptor']['key'] == 'Video':
            item['content_html'] += add_video(article_json['featureMediaPrepared']['heroContent']['descriptor']['props'])
            # TODO: item['_image']
        else:
            item['_image'] = article_json['featureMediaPrepared']['heroContent']['descriptor']['props']['imgSrc']
            item['content_html'] += add_image(article_json['featureMediaPrepared']['heroContent']['descriptor']['props'])

    if article_json.get('text') and 'embed' not in args:
        for block in article_json['text']['descriptor']['children']:
            item['content_html'] += format_block(block)
    elif article_json.get('richTextCaption') and 'embed' not in args:
        for block in article_json['richTextCaption']['descriptor']['children']:
            item['content_html'] += format_block(block)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')


    n = 0
    feed_items = []

    sections = soup.find_all('section', id=re.compile(r'anchor-\d+'))
    if len(sections) > 1:
        n = 5
    else:
        n = 10
    ids = []
    for section in sections:
        m = re.search(r'anchor-(\d+)', section['id'])
        api_url = 'https://www.abc.net.au/news-web/api/loader/channelrefetch?name=PaginationArticles&documentId={0}&prepareParams=%7B%22imagePosition%22%3A%7B%22mobile%22%3A%22right%22%2C%22tablet%22%3A%22right%22%2C%22desktop%22%3A%22right%22%7D%7D&loaderParams=%7B%22pagination%22%3A%7B%22size%22%3A{1}%7D%7D&offset=0&size={1}&total=250'.format(m.group(1), n)
        print(api_url)
        api_json = utils.get_url_json(api_url)
        if api_json:
            for article in api_json['collection']:
                if article['id'] not in ids:
                    ids.append(article['id'])
                    article_url = 'https://www.abc.net.au' + article['link']['to']
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
    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
        feed['title'] = '{} | ABC News'.format(el['content'])
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed