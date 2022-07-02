import json, pytz, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_deployment_value(url):
    page_html = utils.get_url_html(url)
    m = re.search(r'Fusion\.deployment="([^"]+)"', page_html)
    if m:
        return int(m.group(1))
    return -1


def resize_image(image_item, width_target=916):
    if image_item.get('url') and 'washpost' in image_item['url']:
        return 'https://www.washingtonpost.com/wp-apps/imrs.php?src={}&w={}'.format(image_item['url'], width_target)

    img_src = ''
    if image_item.get('image_srcset'):
        img_src = utils.image_from_srcset(image_item['image_srcset'], width_target)
    elif image_item.get('renditions'):
        images = []
        for key, val in image_item['renditions']['original'].items():
            image = {}
            image['width'] = int(key[:-1])
            image['url'] = val
            images.append(image)
        image = utils.closest_dict(images, 'width', width_target)
        img_src = image['url']
    elif image_item.get('resized_urls'):
        images = []
        for key, val in image_item['resized_urls'].items():
            if isinstance(val, dict):
                images.append(val)
            else:
                m = re.search(r'\/resizer\/[^\/]+\/(\d+)x', val)
                if m:
                    image = {}
                    image['url'] = val
                    image['width'] = int(m.group(1))
                    images.append(image)
        image = utils.closest_dict(images, 'width', width_target)
        img_src = image['url']
    elif image_item.get('src'):
        img_src = image_item['src']
    elif image_item.get('url'):
        img_src = image_item['url']
    return img_src


def process_content_element(element, url, func_resize_image, save_debug):
    split_url = urlsplit(url)

    element_html = ''
    if element['type'] == 'text' or element['type'] == 'paragraph':
        # Filter out ad content
        if not re.search(r'adsrv|amzn\.to|fanatics\.com|joinsubtext\.com|lids\.com|nflshop\.com', element['content'], flags=re.I):
            content = re.sub(r'href="/', 'href="https://{}/'.format(split_url.netloc), element['content'])
            element_html += '<p>{}</p>'.format(content)

    elif element['type'] == 'raw_html':
        # Filter out ad content
        if not re.search(r'adsrv|amzn\.to|fanatics\.com|joinsubtext\.com|lids\.com|nflshop\.com', element['content'], flags=re.I):
            raw_soup = BeautifulSoup(element['content'].strip(), 'html.parser')
            if raw_soup.iframe:
                if raw_soup.iframe.get('data-fallback-image-url'):
                    element_html += utils.add_image(raw_soup.iframe['data-fallback-image-url'], link=raw_soup.iframe['src'])
                elif raw_soup.iframe.get('data-url'):
                    data_content = utils.get_content(raw_soup.iframe['data-url'], {}, save_debug)
                    if data_content and data_content.get('_image'):
                        print(data_content['url'])
                        caption = '<a href="{}/content?read&url={}">{}</a>'.format(config.server, quote_plus(data_content['url']), data_content['title'])
                        element_html += utils.add_image(data_content['_image'], caption, link=data_content['url'])
                    else:
                        element_html += '<blockquote><b>Embedded content from <a href="{0}</a>{0}</b></blockquote>'.format(raw_soup.iframe['data-url'])
                else:
                    element_html += utils.add_embed(raw_soup.iframe['src'])
            elif raw_soup.blockquote and raw_soup.blockquote.get('class'):
                if 'tiktok-embed' in raw_soup.blockquote['class']:
                    element_html += utils.add_embed(raw_soup.blockquote['cite'])
            elif raw_soup.script and raw_soup.script.get('src'):
                if 'sendtonews.com' in raw_soup.script['src']:
                    element_html += utils.add_embed(raw_soup.script['src'])
            elif raw_soup.contents[0].name == 'img':
                element_html += utils.add_image(raw_soup.img['src'])
            elif raw_soup.contents[0].name == 'table':
                element_html += element['content']
            elif raw_soup.contents[0].name == 'div' and 'inline-photo' in raw_soup.contents[0].get('class'):
                element_html += utils.add_image(raw_soup.img['src'])
            elif raw_soup.contents[0].name == 'div' and raw_soup.contents[0].get('data-fallback-image-url'):
                element_html += utils.add_image(raw_soup.contents[0]['data-fallback-image-url'])
            elif raw_soup.contents[0].name == 'style':
                # can usually skip these
                pass
            elif element.get('subtype') and element['subtype'] == 'subs_form':
                pass
            else:
                logger.warning('unhandled raw_html ' + element['content'])

    elif element['type'] == 'custom_embed':
        if element['subtype'] == 'custom-audio':
            episode = element['embed']['config']['episode']
            poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(episode['image']))
            element_html += '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><h4>{}</h4><div style="clear:left;"></div><blockquote><small>{}</small></blockquote></div>'.format(
                episode['audio'], poster, episode['title'], episode['summary'])
        elif element['subtype'] == 'magnet':
            pass
        else:
            logger.warning('unhandled custom_embed')

    elif element['type'] == 'divider':
        element_html += '<hr />'

    elif element['type'] == 'correction':
        element_html += '<blockquote><b>{}</b><br>{}</blockquote>'.format(element['correction_type'].upper(),element['text'])

    elif element['type'] == 'quote':
        text = ''
        for el in element['content_elements']:
            text += process_content_element(el, url, func_resize_image, save_debug)
        if element['subtype'] == 'blockquote':
            element_html += utils.add_blockquote(text)
        elif element['subtype'] == 'pullquote':
            element_html += utils.add_pullquote(text)
        else:
            logger.warning('unhandled quote item type {}'.format(element['subtype']))

    elif element['type'] == 'header':
        element_html += '<h{0}>{1}</h{0}>'.format(element['level'], element['content'])

    elif element['type'] == 'oembed_response':
        if element['raw_oembed'].get('_id'):
            element_html += utils.add_embed(element['raw_oembed']['_id'])
        elif element['raw_oembed'].get('url'):
            element_html += utils.add_embed(element['raw_oembed']['url'])
        else:
            logger.warning('unknown raw_oembed url')

    elif element['type'] == 'list':
        if element['list_type'] == 'unordered':
            element_html += '<ul>'
        else:
            element_html += '<ol>'
        for it in element['items']:
            if it['type'] == 'text':
                element_html += '<li>{}</li>'.format(it['content'])
            else:
                # element_html += '<li>Unhandled list item type {}</li>'.format(element['type'])
                logger.warning('unhandled list item type {}'.format(element['type']))
        if element['list_type'] == 'unordered':
            element_html += '</ul>'
        else:
            element_html += '</ol>'

    elif element['type'] == 'table':
        element_html += '<table><tr>'
        for it in element['header']:
            if isinstance(it, str):
                element_html += '<th>{}</th>'.format(it)
            elif isinstance(it, dict) and it.get('type') and it['type'] == 'text':
                element_html += '<th>{}</th>'.format(it['content'])
            else:
                logger.warning('unhandled table header item type {}'.format(element['type']))
        element_html += '</tr>'
        for row in element['rows']:
            element_html += '<tr>'
            for it in row:
                if isinstance(it, str):
                    element_html += '<td>{}</td>'.format(it)
                elif isinstance(it, dict) and it.get('type') and it['type'] == 'text':
                    element_html += '<td>{}</td>'.format(it['content'])
                else:
                    logger.warning('unhandled table row item type {}'.format(element['type']))
            element_html += '</tr>'
        element_html += '</table>'

    elif element['type'] == 'image':
        img_src = func_resize_image(element)
        captions = []
        if element.get('credits_caption_display'):
            captions.append(element['credits_caption_display'])
        else:
            if element.get('caption') and element['caption'] != '-':
                captions.append(element['caption'])
            if element.get('credits') and element['credits'].get('by') and element['credits']['by'][0].get('byline'):
                if element['credits']['by'][0]['byline'] == 'Fanatics':
                    # Skip ad
                    img_src = ''
                else:
                    captions.append(element['credits']['by'][0]['byline'])
        caption = ' | '.join(captions)
        if img_src:
            element_html += utils.add_image(img_src, caption)

    elif element['type'] == 'graphic':
        if element['graphic_type'] == 'image':
            captions = []
            if element.get('title'):
                captions.append(element['title'].capitalize())
            if element.get('byline'):
                captions.append(element['byline'])
            element_html += utils.add_image(element['url'], ' | '.join(captions))
        else:
            logger.warning('unhandled graphic type {}'.format(element['graphic_type']))

    elif element['type'] == 'video':
        if not element.get('streams'):
            if 'washingtonpost.com' in split_url.netloc:
                api_url = 'https://video-api.washingtonpost.com/api/v1/ansvideos/findByUuid?uuid=' + element['_id']
                api_json = utils.get_url_json(api_url)
                if api_json:
                    video_json = api_json[0]
        else:
            video_json = element
        #utils.write_file(video_json, './debug/video.json')
        streams_mp4 = []
        streams_ts = []
        for stream in video_json['streams']:
            if stream['stream_type'] == 'mp4':
                streams_mp4.append(stream)
            elif stream['stream_type'] == 'ts':
                streams_ts.append(stream)
        stream = None
        if streams_mp4:
            stream = utils.closest_dict(streams_mp4, 'height', 720)
            stream_type = 'video/mp4'
        elif streams_ts:
            stream = utils.closest_dict(streams_ts, 'height', 720)
            stream_type = 'application/x-mpegURL'
        if stream:
            if element.get('imageResizerUrls'):
                poster = utils.closest_dict(element['imageResizerUrls'], 'width', 1000)
            elif element.get('promo_image'):
                poster = func_resize_image(element['promo_image'])
            else:
                poster = ''
            element_html += utils.add_video(stream['url'], stream_type, poster, element['headlines']['basic'])
        else:
            logger.warning('unhandled video streams')

    elif element['type'] == 'social_media' and element['sub_type'] == 'twitter':
        links = BeautifulSoup(element['html'], 'html.parser').find_all('a')
        element_html += utils.add_embed(links[-1])

    elif element['type'] == 'story':
        # This may be Wapo specific
        headline = element['headlines']['basic']
        if '<' in headline:
            # Couple of cases of unclosed html tags in the headline, just use the text
            headline = BeautifulSoup(headline, 'html.parser').get_text()
        element_html += '<hr><h2>{}</h2>'.format(headline)
        authors = []
        for author in element['credits']['by']:
            authors.append(author['name'])
        tz_est = pytz.timezone('US/Eastern')
        dt = datetime.fromisoformat(element['display_date'].replace('Z', '+00:00')).astimezone(tz_est)
        date = utils.format_display_date(dt)
        #date = '{}. {}, {} {}'.format(dt.strftime('%b'), dt.day, dt.year, dt.strftime('%I:%M %p').lstrip('0'))
        if authors:
            byline = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
            element_html += '<p>by {} (updated {})</p>'.format(byline, date)
        else:
            element_html += '<p>updated {}</p>'.format(date)
        element_html += get_content_html(element, func_resize_image, url, save_debug)

    elif element['type'] == 'interstitial_link':
        pass

    else:
        logger.warning('unhandled element type {}'.format(element['type']))
    return element_html


def get_content_html(content, func_resize_image, url, save_debug):
    content_html = ''
    if content['type'] == 'video':
        streams_mp4 = []
        streams_ts = []
        for stream in content['streams']:
            if stream['stream_type'] == 'mp4':
                streams_mp4.append(stream)
            elif stream['stream_type'] == 'ts':
                streams_ts.append(stream)
        stream = None
        if streams_mp4:
            stream = utils.closest_dict(streams_mp4, 'height', 720)
            stream_type = 'video/mp4'
        elif streams_ts:
            stream = utils.closest_dict(streams_ts, 'height', 720)
            stream_type = 'application/x-mpegURL'
        if stream:
            if content.get('imageResizerUrls'):
                poster = utils.closest_dict(content['imageResizerUrls'], 'width', 1000)
            elif content.get('promo_image'):
                poster = func_resize_image(content['promo_image'])
            else:
                poster = ''
            if content.get('description'):
                caption = content['description']['basic']
            else:
                caption = ''
            content_html += utils.add_video(stream['url'], stream_type, poster, caption)
        else:
            logger.warning('no handled streams found for video content in ' + url)
        return content_html

    if content.get('summary'):
        content_html += '<ul>'
        for it in content['summary']:
            if it.get('link'):
                content_html += '<li><a href="{}">{}</a></li>'.format(it['link'], it['description'])
            else:
                content_html += '<li>{}</li>'.format(it['description'])
        content_html += '</ul>'

    # Add a lead image if it's not in the article (except galleries because those are moved to the end)
    if content['type'] != 'video':
        if content['content_elements'][0]['type'] != 'image' and content['content_elements'][0]['type'] != 'video' and content['content_elements'][0].get('subtype') != 'youtube':
            if content.get('multimedia_main'):
                if content['multimedia_main']['type'] == 'gallery':
                    content_html += process_content_element(content['multimedia_main']['content_elements'][0], url, func_resize_image, save_debug)
                else:
                    content_html += process_content_element(content['multimedia_main'], url, func_resize_image, save_debug)
            else:
                if content.get('promo_items'):
                    lead_image = None
                    if content['promo_items'].get('basic') and content['promo_items']['basic']['type'] == 'image':
                        lead_image = content['promo_items']['basic']
                    elif content['promo_items'].get('images'):
                        lead_image = content['promo_items']['images'][0]
                    if lead_image:
                        content_html += process_content_element(lead_image, url, func_resize_image, save_debug)

    gallery_elements = []
    for element in content['content_elements']:
        # Add galleries to the end of the content
        if element['type'] == 'gallery':
            gallery_elements.append(element)
        else:
            content_html += process_content_element(element, url, func_resize_image, save_debug)

    if content.get('multimedia_main'):
        if content['multimedia_main']['type'] == 'gallery':
            gallery_elements.append(content['multimedia_main'])
    elif content.get('related_content') and content['related_content'].get('galleries'):
        for gallery in content['related_content']['galleries']:
            gallery_elements.append(gallery)

    if len(gallery_elements) > 0:
        for gallery in gallery_elements:
            content_html += '<h3>Photo Gallery ({} photos)</h3>'.format(len(gallery['content_elements']))
            for element in gallery['content_elements']:
                content_html += process_content_element(element, url, func_resize_image, save_debug) + '<br/>'

    # Reuters specific
    if content.get('related_content') and content['related_content'].get('videos'):
        content_html += '<h3>Related Videos</h3>'
        for video in content['related_content']['videos']:
            caption = '<b>{}</b> &mdash; {}'.format(video['title'], video['description'])
            content_html += utils.add_video(video['source']['mp4'], 'video/mp4', video['thumbnail']['renditions']['original']['480w'], caption) + '<br/>'
    return content_html


def get_item(content, url, args, save_debug):
    item = {}
    if content.get('_id'):
        item['id'] = content['_id']
    elif content.get('id'):
        item['id'] = content['id']
    else:
        item['id'] = url

    item['url'] = url
    if content.get('headlines'):
        item['title'] = content['headlines']['basic']
    elif content.get('title'):
        item['title'] = content['title']

    if content.get('first_publish_date'):
        dt = datetime.fromisoformat(content['first_publish_date'].replace('Z', '+00:00'))
    elif content.get('published_time'):
        dt = datetime.fromisoformat(content['published_time'].replace('Z', '+00:00'))
    elif content.get('display_date'):
        dt = datetime.fromisoformat(content['display_date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    dt = None
    if content.get('last_updated_date'):
        dt = datetime.fromisoformat(content['last_updated_date'].replace('Z', '+00:00'))
    elif content.get('updated_time'):
        dt = datetime.fromisoformat(content['updated_time'].replace('Z', '+00:00'))
    if dt:
        item['date_modified'] = dt.isoformat()

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    authors = []
    if content.get('credits'):
        for author in content['credits']['by']:
            authors.append(author['name'])
    elif content.get('authors'):
        for author in content['authors']:
            authors.append(author['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    tags = []
    if content.get('taxonomy'):
        for key, val in content['taxonomy'].items():
            if isinstance(val, dict) and val.get('name'):
                if not re.search('advertising|blocklists|EXCLUDE|INCLUDE|iptc-media|Safe from|TRBC', val['name']):
                    tags.append(val['name'])
            elif isinstance(val, list):
                for it in val:
                    if isinstance(it, dict) and it.get('name'):
                        if not re.search('advertising|blocklists|EXCLUDE|INCLUDE|iptc-media|Safe from|TRBC', it['name']):
                            tags.append(it['name'])
    if content.get('websites'):
        for key, val in content['websites'].items():
            if val.get('website_section'):
                tags.append(val['website_section']['name'])
    if tags:
        item['tags'] = list(set(tags))

    if content.get('promo_items'):
        if content['promo_items'].get('basic') and content['promo_items']['basic']['type'] == 'image':
            item['_image'] = content['promo_items']['basic']['url']
        elif content['promo_items'].get('images'):
            item['_image'] = content['promo_items']['images'][0]['url']
    elif content.get('content_elements'):
        if content['content_elements'][0]['type'] == 'image':
            item['_image'] = resize_image(content['content_elements'][0])
        elif content['content_elements'][0]['type'] == 'video':
            if content['content_elements'][0].get('imageResizerUrls'):
                item['_image'] = utils.closest_dict(content['content_elements'][0]['imageResizerUrls'], 'width', 1000)
            elif content['content_elements'][0].get('promo_image'):
                item['_image'] = resize_image(content['content_elements'][0]['promo_image'])

    if content.get('description'):
        if isinstance(content['description'], str):
            item['summary'] = content['description']
        elif isinstance(content['description'], dict):
            item['summary'] = content['description']['basic']

    item['content_html'] = get_content_html(content, resize_image, url, save_debug)
    return item


def get_content(url, args, save_debug=False):
    if not url.startswith('http'):
        return None
    split_url = urlsplit(url)
    tld = tldextract.extract(url)
    sites_json = utils.read_json_file('./sites.json')
    d = sites_json[tld.domain]['deployment']

    for n in range(2):
        query = re.sub(r'\s', '', json.dumps(sites_json[tld.domain]['content']['query'])).replace('PATH', split_url.path)
        api_url = '{}{}?query={}&d={}&_website={}'.format(sites_json[tld.domain]['api_url'], sites_json[tld.domain]['content']['source'], quote_plus(query), d, sites_json[tld.domain]['arc_site'])
        if save_debug:
            logger.debug('getting content from ' + api_url)

        api_json = utils.get_url_json(api_url)
        if api_json:
            break
        elif n == 0:
            # Failed...try new deployment value
            d = get_deployment_value(url)
            if d > 0 and d != sites_json[tld.domain]['deployment']:
                sites_json[tld.domain]['deployment'] = d
                utils.write_file(sites_json, './sites.json')
                logger.warning('retrying with new deployment value {}'.format(d))
            else:
                return None
        else:
            return None

    if api_json.get('items'):
        content = api_json['items'][0]
    else:
        content = api_json

    if save_debug:
        utils.write_file(content, './debug/debug.json')

    if content.get('result'):
        return get_item(content['result'], url, args, save_debug)
    return get_item(content, url, args, save_debug)


def get_feed(args, save_debug=False):
    # https://www.baltimoresun.com/rss/
    # https://www.baltimoresun.com/arcio/rss/
    # https://feeds.washingtonpost.com/rss/business/technology/

    if '/rss/' in args['url']:
        return rss.get_feed(args, save_debug, get_content)

    tld = tldextract.extract(args['url'])
    sites_json = utils.read_json_file('./sites.json')
    d = sites_json[tld.domain]['deployment']

    split_url = urlsplit(args['url'])
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    paths = list(filter(None, path.split('/')))

    for n in range(2):
        if len(paths) == 0:
            source = sites_json[tld.domain]['homepage_feed']['source']
            query = re.sub(r'\s', '', json.dumps(sites_json[tld.domain]['homepage_feed']['query']))
        elif re.search(r'author|people|staff', paths[0]):
            if len(paths) > 1:
                author = paths[1]
            else:
                # https://www.baltimoresun.com/bal-nathan-ruiz-20190328-staff.html
                m = re.search(r'(.*)-staff\.html', paths[0])
                if m:
                    author = m.group(1)
                else:
                    logger.warning('unhandled author url ' + args['url'])
                    return None
            source = sites_json[tld.domain]['author_feed']['source']
            query = re.sub(r'\s', '', json.dumps(sites_json[tld.domain]['author_feed']['query'])).replace('AUTHOR', author)
        elif paths[0] == 'tags' or paths[0] == 'topic':
            tag = paths[1]
            source = sites_json[tld.domain]['tag_feed']['source']
            query = re.sub(r'\s', '', json.dumps(sites_json[tld.domain]['tag_feed']['query'])).replace('TAG', tag)
        else:
            if split_url.path.endswith('/'):
                path = split_url.path[:-1]
            else:
                path = split_url.path
            source = sites_json[tld.domain]['section_feed']['source']
            if 'washingtonpost' in split_url.netloc:
                page_html = utils.get_url_html(args['url'])
                if not page_html:
                    return None
                query = ''
                for m in re.findall(r'"_admin":({[^}]+})', page_html):
                    admin = json.loads(m)
                    if path in admin['alias_ids']:
                        query = '{{"query":"{}"}}'.format(re.sub(r'limit=\d+', 'limit=10', admin['default_content']))
                        break
                if not query:
                    m = re.search(r'(prism://prism\.query/[^&]+)', page_html)
                    if m:
                        query = '{{"query":"{}"}}'.format(m.group(1) + '&limit=10')
                if not query:
                    logger.warning('unknown feed for ' + args['url'])
                    return None
            else:
                section = paths[-1]
                query = re.sub(r'\s', '', json.dumps(sites_json[tld.domain]['section_feed']['query'])).replace('PATH', path).replace('SECTION', section)

        api_url = '{}{}?query={}&d={}&_website={}'.format(sites_json[tld.domain]['api_url'], source, quote_plus(query), d, sites_json[tld.domain]['arc_site'])
        if save_debug:
            logger.debug('getting feed from ' + api_url)

        feed_content = utils.get_url_json(api_url)
        if feed_content:
            break
        elif n == 0:
            # Failed...try new deployment value
            d = get_deployment_value(args['url'])
            if d > 0 and d != sites_json[tld.domain]['deployment']:
                sites_json[tld.domain]['deployment'] = d
                utils.write_file(sites_json, './sites.json')
                logger.warning('retrying with new deployment value {}'.format(d))
            else:
                return None
        else:
            return None

    if save_debug:
        utils.write_file(feed_content, './debug/feed.json')

    feed_title = ''
    if isinstance(feed_content, dict):
        if feed_content.get('content_elements'):
            content_elements = feed_content['content_elements']
        elif feed_content.get('stories'):
            content_elements = feed_content['stories']
        elif feed_content.get('result'):
            content_elements = feed_content['result']['articles']
            if feed_content['result'].get('section'):
                feed_title = 'Reuters > ' + feed_content['result']['section']['name']
        elif feed_content.get('latest'):
            content_elements = feed_content['latest']
        elif feed_content.get('items'):
            content_elements = feed_content['items']
    else:
        content_elements = feed_content

    n = 0
    items = []
    for content in content_elements:
        if content.get('canonical_url'):
            url = content['canonical_url']
        elif content.get('website_url'):
            url = content['website_url']
        elif content.get('url'):
            url = content['url']
        if url.startswith('/'):
            url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, url)

        # Check age
        if args.get('age'):
            item = {}
            if content.get('first_publish_date'):
                date = content['first_publish_date']
            elif content.get('published_time'):
                date = content['published_time']
            elif content.get('display_date'):
                date = content['display_date']
            dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
            item['_timestamp'] = dt.timestamp()
            if not utils.check_age(item, args):
                if save_debug:
                    logger.debug('skipping old article ' + url)
                continue
        if save_debug:
            logger.debug('getting content from ' + url)
        if content.get('content_elements') and (content['content_elements'][0].get('content') or content['content_elements'][0]['type'] == 'image' or content['content_elements'][0]['type'] == 'video'):
            item = get_item(content, url, args, save_debug)
        elif content.get('type') and content['type'] == 'video' and content.get('streams'):
            item = get_item(content, url, args, save_debug)
        else:
            item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = items.copy()
    return feed


def test_handler():
    feeds = ['https://feeds.washingtonpost.com/rss/homepage',
             'https://www.washingtonpost.com/business/technology/',
             'https://www.washingtonpost.com/opinions/',
             'https://www.reuters.com/technology']
    for url in feeds:
        get_feed({"url": url}, True)
