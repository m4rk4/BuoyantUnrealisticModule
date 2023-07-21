import base64, hashlib, hmac, json, pytz, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote, quote_plus

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


def resize_image(image_item, site_json, width=1280):
    img_src = ''
    if image_item.get('url') and 'washpost' in image_item['url']:
        if width == 1280:
            width = 916
        img_src = 'https://www.washingtonpost.com/wp-apps/imrs.php?src={}&w={}'.format(quote_plus(image_item['url']), width)
    elif site_json.get('resize_image'):
        query = re.sub(r'\s', '', json.dumps(site_json['resize_image']['query'])).replace('SRC', image_item['url'])
        api_url = '{}{}?query={}&d={}&_website={}'.format(site_json['api_url'], site_json['resize_image']['source'], quote_plus(query), site_json['deployment'], site_json['arc_site'])
        api_json = utils.get_url_json(api_url)
        if api_json:
            images = []
            for key, val in api_json.items():
                m = re.search(r'(\d+)x(\d+)', key)
                if m and m.group(2) == '0':
                    img = {
                        "width": int(m.group(1)),
                        "path": val.replace('=filters:', '=/{}/filters:'.format(key))
                    }
                    images.append(img)
            if images:
                split_url = urlsplit(image_item['url'])
                img = utils.closest_dict(images, 'width', width)
                img_src = site_json['resizer_url'] + img['path'] + split_url.netloc + split_url.path
    elif site_json.get('resizer_secret'):
        split_url = urlsplit(image_item['url'])
        if split_url.path.startswith('/resizer'):
            m = re.search(r'/([^/]+(advancelocal|arcpublishing).*)', split_url.path)
            if not m:
                logger.warning('unable to determine image path in ' + image_item['url'])
                return image_item['url']
            image_path = m.group(1)
        else:
            image_path = '{}{}'.format(split_url.netloc, split_url.path)
        operation_path = '{}x0/smart/'.format(width)
        # THUMBOR_SECURITY_KEY (from tampabay.com)
        #security_key = 'Fmkgru2rZ2uPZ5wXs7B2HbVDHS2SZuA7'
        hashed = hmac.new(bytes(site_json['resizer_secret'], 'ascii'), bytes(operation_path+image_path, 'ascii'), hashlib.sha1)
        #resizer_hash = base64.b64encode(hashed.digest()).decode().replace('+', '-').replace('/', '_')
        resizer_hash = base64.urlsafe_b64encode(hashed.digest()).decode()
        img_src = '{}{}/{}{}'.format(site_json['resizer_url'], resizer_hash, operation_path, image_path)
    elif image_item.get('renditions'):
        images = []
        for key, val in image_item['renditions']['original'].items():
            image = {
                "width": int(key[:-1]),
                "url": val
            }
            images.append(image)
        image = utils.closest_dict(images, 'width', width)
        img_src = image['url']
    if not img_src:
        img_src = image_item['url']
    return img_src


def process_content_element(element, url, site_json, save_debug):
    split_url = urlsplit(url)

    element_html = ''
    if element['type'] == 'text' or element['type'] == 'paragraph':
        # Filter out ad content
        if not re.search(r'adsrv|amzn\.to|fanatics\.com|joinsubtext\.com|lids\.com|nflshop\.com', element['content'], flags=re.I):
            content = re.sub(r'href="/', 'href="https://{}/'.format(split_url.netloc), element['content'])
            element_html += '<p>{}</p>'.format(content)

    elif element['type'] == 'raw_html':
        # Filter out ad content
        if not re.search(r'adsrv|amzn\.to|EMAIL/TWITTER|fanatics\.com|joinsubtext\.com|lids\.com|link\.[^\.]+\.com/s/Newsletter|mass-live-fanduel|nflshop\.com|\boffer\b|subscriptionPanel|tarot\.com', element['content'], flags=re.I):
            raw_soup = BeautifulSoup(element['content'].strip(), 'html.parser')
            if raw_soup.iframe:
                if raw_soup.iframe.get('data-fallback-image-url'):
                    element_html += utils.add_image(raw_soup.iframe['data-fallback-image-url'], link=raw_soup.iframe['src'])
                elif raw_soup.iframe.get('data-url'):
                    data_content = utils.get_content(raw_soup.iframe['data-url'], {}, save_debug)
                    if data_content and data_content.get('_image'):
                        #print(data_content['url'])
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
            elif raw_soup.find('aside', class_='refer'):
                it = raw_soup.find('aside', class_='refer')
                element_html += utils.add_blockquote(it.decode_contents())
            elif raw_soup.contents[0].name == 'img':
                element_html += utils.add_image(raw_soup.img['src'])
            elif raw_soup.contents[0].name == 'table':
                element_html += element['content']
            elif raw_soup.contents[0].name == 'div' and 'inline-photo' in raw_soup.contents[0].get('class'):
                element_html += utils.add_image(raw_soup.img['src'])
            elif raw_soup.contents[0].name == 'div' and raw_soup.contents[0].get('data-fallback-image-url'):
                element_html += utils.add_image(raw_soup.contents[0]['data-fallback-image-url'])
            elif raw_soup.contents[0].name == 'hl2':
                element_html += element['content'].replace('hl2', 'h2')
            elif raw_soup.contents[0].name == 'style':
                # can usually skip these
                pass
            elif element.get('subtype') and element['subtype'] == 'subs_form':
                pass
            else:
                #element_html += '<p>{}</p>'.format(element['content'])
                logger.warning('unhandled raw_html ')
                print(element['content'])

    elif element['type'] == 'custom_embed':
        if element['subtype'] == 'custom-image':
            captions = []
            if element['embed']['config'].get('image_caption'):
                captions.append(element['embed']['config']['image_caption'])
            if element['embed']['config'].get('image_credit'):
                captions.append(element['embed']['config']['image_credit'])
            img_src = resize_image({"url": element['embed']['config']['image_src']}, site_json)
            element_html += utils.add_image(img_src, ' | '.join(captions))
        elif element['subtype'] == 'custom-audio':
            episode = element['embed']['config']['episode']
            poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(episode['image']))
            element_html += '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><h4>{}</h4><div style="clear:left;"></div><blockquote><small>{}</small></blockquote></div>'.format(
                episode['audio'], poster, episode['title'], episode['summary'])
        elif element['subtype'] == 'datawrapper':
            element_html += utils.add_embed(element['embed']['url'])
        elif re.search(r'iframe', element['subtype'], flags=re.I):
            embed_html = base64.b64decode(element['embed']['config']['base64HTML']).decode('utf-8')
            m = re.search(r'src="([^"]+)"', embed_html)
            if m:
                element_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled custom_embed iframe')
        elif element['subtype'] == 'magnet' or element['subtype'] == 'newsletter_signup' or element['subtype'] == 'related_story' or element['subtype'] == 'SubjectTag':
            pass
        else:
            logger.warning('unhandled custom_embed ' + element['subtype'])

    elif element['type'] == 'divider':
        element_html += '<hr />'

    elif element['type'] == 'correction':
        element_html += '<blockquote><b>{}</b><br>{}</blockquote>'.format(element['correction_type'].upper(),element['text'])

    elif element['type'] == 'quote':
        text = ''
        for el in element['content_elements']:
            text += process_content_element(el, url, site_json, save_debug)
        if element.get('citation'):
            cite = element['citation']['content']
        else:
            cite = ''
        if element.get('subtype'):
            if element['subtype'] == 'blockquote':
                element_html += utils.add_blockquote(text)
            elif element['subtype'] == 'pullquote':
                element_html += utils.add_pullquote(text, cite)
            else:
                logger.warning('unhandled quote item type {}'.format(element['subtype']))
        else:
            element_html += utils.add_pullquote(text, cite)

    elif element['type'] == 'header':
        element_html += '<h{0}>{1}</h{0}>'.format(element['level'], element['content'])

    elif element['type'] == 'oembed_response':
        if element['raw_oembed'].get('_id') and element['raw_oembed']['_id'].startswith('http'):
            element_html += utils.add_embed(element['raw_oembed']['_id'])
        elif element['raw_oembed'].get('url') and element['raw_oembed']['url'].startswith('http'):
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
        element_html += '<table>'
        if element.get('header'):
            element_html += '<tr>'
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
        img_src = resize_image(element, site_json)
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
        #if element.get('subtitle') and element['subtitle'].strip():
        #    caption = '<strong>{}.</strong> '.format(element['subtitle'].strip()) + caption
        if img_src:
            element_html += utils.add_image(img_src, caption)

    elif element['type'] == 'gallery':
        img_src = resize_image(element['content_elements'][0], site_json)
        link = '{}://{}'.format(split_url.scheme, split_url.netloc)
        if element.get('canonical_url'):
            link += element['canonical_url']
        elif element.get('slug'):
            link += element['slug']
        caption = '<strong>Gallery:</strong> <a href="{}">{}</a>'.format(link, element['headlines']['basic'])
        link = '{}/content?read&url={}'.format(config.server, quote_plus(link))
        if img_src:
            element_html += utils.add_image(img_src, caption, link=link)

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
        if 'washingtonpost.com' in split_url.netloc:
            api_url = 'https://video-api.washingtonpost.com/api/v1/ansvideos/findByUuid?uuid=' + element['_id']
            api_json = utils.get_url_json(api_url)
            if api_json:
                video_json = api_json[0]
        elif not element.get('streams'):
            api_url = '{}video-by-id?query=%7B%22id%22%3A%22{}%22%7D&d={}&_website={}'.format(site_json['api_url'], element['_id'], site_json['deployment'], site_json['arc_site'])
            api_json = utils.get_url_json(api_url)
            if api_json:
                video_json = api_json
        else:
            video_json = element
        #utils.write_file(video_json, './debug/video.json')
        streams_mp4 = []
        streams_ts = []
        for stream in video_json['streams']:
            if stream.get('stream_type'):
                if stream['stream_type'] == 'mp4':
                    streams_mp4.append(stream)
                elif stream['stream_type'] == 'ts':
                    streams_ts.append(stream)
            else:
                if re.search(r'\.mp4', stream['url']):
                    streams_mp4.append(stream)
                elif re.search(r'\.m3u8', stream['url']):
                    streams_ts.append(stream)
        stream = None
        if streams_mp4:
            if streams_mp4[0].get('height'):
                stream = utils.closest_dict(streams_mp4, 'height', 720)
            else:
                stream = streams_mp4[0]
            stream_type = 'video/mp4'
        elif streams_ts:
            if streams_ts[0].get('height'):
                stream = utils.closest_dict(streams_ts, 'height', 720)
            else:
                stream = streams_ts[0]
            stream_type = 'application/x-mpegURL'
        if stream:
            if element.get('imageResizerUrls'):
                poster = utils.closest_dict(element['imageResizerUrls'], 'width', 1000)
            elif element.get('promo_image'):
                poster = resize_image(element['promo_image'], site_json)
            else:
                poster = ''
            element_html += utils.add_video(stream['url'], stream_type, poster, element['headlines']['basic'])
        else:
            logger.warning('unhandled video streams')

    elif element['type'] == 'social_media' and element['sub_type'] == 'twitter':
        links = BeautifulSoup(element['html'], 'html.parser').find_all('a')
        element_html += utils.add_embed(links[-1]['href'])

    elif element['type'] == 'reference':
        if element.get('referent') and element['referent'].get('id'):
            element_html += utils.add_embed(element['referent']['id'])
        else:
            logger.warning('unhandled reference element')

    elif element['type'] == 'story':
        # This may be Wapo specific
        headline = element['headlines']['basic']
        if '<' in headline:
            # Couple of cases of unclosed html tags in the headline, just use the text
            headline = BeautifulSoup(headline, 'html.parser').get_text()
        element_html += '<hr><h2>{}</h2>'.format(headline)
        authors = []
        for author in element['credits']['by']:
            if author.get('name'):
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
        element_html += get_content_html(element, url, site_json, save_debug)

    elif element['type'] == 'interstitial_link':
        pass

    else:
        logger.warning('unhandled element type {}'.format(element['type']))
        #print(element)
    return element_html


def get_content_html(content, url, site_json, save_debug):
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
                poster = resize_image(content['promo_image'], site_json)
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

    if content.get('subheadlines'):
        content_html += '<p><em>{}</em></p>'.format(content['subheadlines']['basic'])

    if content.get('summary'):
        content_html += '<ul>'
        for it in content['summary']:
            if it.get('link'):
                content_html += '<li><a href="{}">{}</a></li>'.format(it['link'], it['description'])
            else:
                content_html += '<li>{}</li>'.format(it['description'])
        content_html += '</ul>'

    lead_image = None
    if content.get('multimedia_main'):
        lead_image = content['multimedia_main']
    elif content.get('promo_items'):
        if content['promo_items'].get('youtube'):
            content_html += utils.add_embed(content['promo_items']['youtube']['content'])
        elif content['promo_items'].get('lead_art'):
            lead_image = content['promo_items']['lead_art']
        elif content['promo_items'].get('basic'):
            lead_image = content['promo_items']['basic']
        elif content['promo_items'].get('images'):
            lead_image = content['promo_items']['images'][0]
    if lead_image:
        if content['type'] == 'gallery' or (content['content_elements'][0]['type'] != 'image' and content['content_elements'][0]['type'] != 'video' and content['content_elements'][0].get('subtype') != 'youtube'):
            content_html += process_content_element(lead_image, url, site_json, save_debug)

    for element in content['content_elements']:
        content_html += process_content_element(element, url, site_json, save_debug)

    if content.get('related_content') and content['related_content'].get('galleries'):
        for gallery in content['related_content']['galleries']:
            if gallery.get('canonical_url'):
                content_html += process_content_element(gallery, url, site_json, save_debug)
            else:
                content_html += '<h3>Photo Gallery</h3>'
                for element in gallery['content_elements']:
                    if lead_image and lead_image['id'] == element['id']:
                        continue
                    content_html += process_content_element(element, url, site_json, save_debug)

    # Reuters specific
    if content.get('related_content') and content['related_content'].get('videos'):
        content_html += '<h3>Related Videos</h3>'
        for video in content['related_content']['videos']:
            caption = '<b>{}</b> &mdash; {}'.format(video['title'], video['description'])
            content_html += utils.add_video(video['source']['mp4'], 'video/mp4', video['thumbnail']['renditions']['original']['480w'], caption)

    content_html = re.sub(r'</figure><(figure|table)', r'</figure><br/><\1', content_html)
    return content_html


def get_item(content, url, args, site_json, save_debug):
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

    date = ''
    if content.get('first_publish_date'):
        date = content['first_publish_date']
    elif content.get('published_time'):
        date = content['published_time']
    elif content.get('display_date'):
        date = content['display_date']
    if date:
        dt = datetime.fromisoformat(re.sub(r'(\.\d+)?Z$', '+00:00', date))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    else:
        logger.warning('no publish date found in ' + item['url'])

    date = ''
    if content.get('last_updated_date'):
        date = content['last_updated_date']
    elif content.get('updated_time'):
        date = content['updated_time']
    elif content.get('display_date'):
        date = content['display_date']
    if date:
        dt = datetime.fromisoformat(re.sub(r'(\.\d+)?Z$', '+00:00', date))
        item['date_modified'] = dt.isoformat()
    else:
        logger.warning('no updated date found in ' + item['url'])

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    authors = []
    if content.get('credits') and content['credits'].get('by'):
        for author in content['credits']['by']:
            authors.append(author['name'])
    elif content.get('authors'):
        for author in content['authors']:
            authors.append(author['name'])
    elif content.get('distributor'):
        authors.append(content['distributor']['name'])
    if authors:
        item['author'] = {}
        if len(authors) == 1:
            item['author']['name'] = authors[0]
        else:
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
            if val.get('website_section') and val['website_section'].get('name'):
                if val['website_section']['name'] not in tags:
                    tags.append(val['website_section']['name'])
    if tags:
        item['tags'] = list(set(tags))

    if content.get('promo_items'):
        if content['promo_items'].get('basic') and content['promo_items']['basic']['type'] == 'image':
            item['_image'] = resize_image(content['promo_items']['basic'], site_json)
        elif content['promo_items'].get('basic') and content['promo_items']['basic']['type'] == 'gallery':
            item['_image'] = resize_image(content['promo_items']['basic']['promo_items']['basic'], site_json)
        elif content['promo_items'].get('basic') and content['promo_items']['basic']['type'] == 'video':
            item['_image'] = resize_image(content['promo_items']['basic']['promo_items']['basic'], site_json)
        elif content['promo_items'].get('images'):
            item['_image'] = resize_image(content['promo_items']['images'][0], site_json)
    elif content.get('content_elements'):
        if content['content_elements'][0]['type'] == 'image':
            item['_image'] = resize_image(content['content_elements'][0], site_json)
        elif content['content_elements'][0]['type'] == 'video':
            if content['content_elements'][0].get('imageResizerUrls'):
                item['_image'] = utils.closest_dict(content['content_elements'][0]['imageResizerUrls'], 'width', 1000)
            elif content['content_elements'][0].get('promo_image'):
                item['_image'] = resize_image(content['content_elements'][0]['promo_image'], site_json)

    if content.get('description'):
        if isinstance(content['description'], str):
            item['summary'] = content['description']
        elif isinstance(content['description'], dict):
            item['summary'] = content['description']['basic']

    item['content_html'] = get_content_html(content, url, site_json, save_debug)
    return item


def get_content(url, args, site_json, save_debug=False):
    if not url.startswith('http'):
        return None
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    paths = list(filter(None, split_url.path[1:].split('/')))

    for n in range(2):
        query = re.sub(r'\s', '', json.dumps(site_json['content']['query'])).replace('PATH', path)
        if re.search(r'ajc\.com|daytondailynews\.com', split_url.netloc):
            query = query.replace('ID', paths[-1])
        api_url = '{}{}?query={}&d={}&_website={}'.format(site_json['api_url'], site_json['content']['source'], quote_plus(query), site_json['deployment'], site_json['arc_site'])
        if save_debug:
            logger.debug('getting content from ' + api_url)
        api_json = utils.get_url_json(api_url)
        if api_json:
            break
        elif n == 0:
            # Failed...try new deployment value
            d = get_deployment_value(url)
            if d > 0 and d != site_json['deployment']:
                logger.debug('retrying with new deployment value {}'.format(d))
                site_json['deployment'] = d
                utils.update_sites(url, site_json)
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
        return get_item(content['result'], url, args, site_json, save_debug)
    return get_item(content, url, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    paths = list(filter(None, path.split('/')))

    # https://www.baltimoresun.com/rss/
    # https://www.baltimoresun.com/arcio/rss/
    # https://feeds.washingtonpost.com/rss/business/technology/
    # https://www.washingtonpost.com/news/powerpost/feed/
    if 'rss' in paths or 'feed' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    for n in range(2):
        if len(paths) == 0:
            source = site_json['homepage_feed']['source']
            query = re.sub(r'\s', '', json.dumps(site_json['homepage_feed']['query']))
        elif re.search(r'about|author|people|staff|team', paths[0]):
            if paths[0] == 'about':
                # https://www.bostonglobe.com/about/staff-list/columnist/dan-shaughnessy/
                author = paths[-1]
            elif len(paths) > 1:
                # https://www.cleveland.com/staff/tpluto/posts.html
                author = paths[1]
            else:
                # https://www.baltimoresun.com/bal-nathan-ruiz-20190328-staff.html
                m = re.search(r'(.*)-staff\.html', paths[0])
                if m:
                    author = m.group(1)
                else:
                    logger.warning('unhandled author url ' + args['url'])
                    return None
            source = site_json['author_feed']['source']
            query = re.sub(r'\s', '', json.dumps(site_json['author_feed']['query'])).replace('AUTHOR', author).replace('PATH', path).replace('%20', ' ')
        elif paths[0] == 'tags' or paths[0] == 'tag' or paths[0] == 'topics' or (paths[0] == 'topic' and 'thebaltimorebanner' not in split_url.netloc):
            tag = paths[1]
            source = site_json['tag_feed']['source']
            query = re.sub(r'\s', '', json.dumps(site_json['tag_feed']['query'])).replace('TAG', tag).replace('PATH', path).replace('%20', ' ')
        elif split_url.netloc == 'www.reuters.com' and split_url.path.startswith('/markets/companies/'):
            tag = paths[-1]
            source = site_json['stock_symbol_feed']['source']
            query = re.sub(r'\s', '', json.dumps(site_json['stock_symbol_feed']['query'])).replace('SYMBOL', tag).replace('PATH', path).replace('%20', ' ')
        else:
            if site_json.get('section_feed'):
                source = site_json['section_feed']['source']
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
                    section_path = path.replace('/section', '')
                    query = re.sub(r'\s', '', json.dumps(site_json['section_feed']['query'])).replace('SECTIONPATH', section_path).replace('SECTION', section).replace('PATH', path).replace('%20', ' ')
            elif site_json.get('sections') and site_json['sections'].get(paths[-1]):
                section = paths[-1]
                source = site_json['sections'][section]['source']
                query = re.sub(r'\s', '', json.dumps(site_json['sections'][section]['query'])).replace('SECTION', section).replace('PATH', path).replace('%20', ' ')

        api_url = '{}{}?query={}&d={}&_website={}'.format(site_json['api_url'], source, quote_plus(query), site_json['deployment'], site_json['arc_site'])
        if save_debug:
            logger.debug('getting feed from ' + api_url)

        feed_content = utils.get_url_json(api_url)
        if feed_content:
            break
        elif n == 0:
            # Failed...try new deployment value
            d = get_deployment_value(args['url'])
            if d > 0 and d != site_json['deployment']:
                logger.debug('retrying with new deployment value {}'.format(d))
                site_json['deployment'] = d
                utils.update_sites(args['url'], site_json)
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
        elif content.get('websites') and content['websites'].get(site_json['arc_site']) and content['websites'][site_json['arc_site']].get('website_url'):
            url = content['websites'][site_json['arc_site']]['website_url']

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

        if not content.get('type'):
            item = get_content(url, args, site_json, save_debug)
        elif content.get('content_elements') and (content['content_elements'][0].get('content') or content['content_elements'][0]['type'] == 'image' or content['content_elements'][0]['type'] == 'video'):
            item = get_item(content, url, args, site_json, save_debug)
        elif content.get('type') and content['type'] == 'video' and content.get('streams'):
            item = get_item(content, url, args, site_json, save_debug)
        else:
            item = get_content(url, args, site_json, save_debug)

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
