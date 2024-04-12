import copy, html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import datawrapper, rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    if split_url.netloc == 'dynaimage.cdn.cnn.com':
        paths = list(filter(None, split_url.path[1:].split('/')))
        return 'https://dynaimage.cdn.cnn.com/{}/q_auto,w_{},c_fit/{}'.format('/'.join(paths[:-2]), width, paths[-1])
    return '{}://{}{}?c=original&q=w_{},c_fill'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def get_resized_image(image_cuts, width=1000):
    images = []
    for key, img in image_cuts.items():
        if img['uri'].startswith('https://dynaimage.cdn.cnn.com'):
            return resize_image(img['uri'], width)
        images.append(img)
    img = utils.closest_dict(images, 'width', width)
    if img['uri'].startswith('//'):
        img_src = 'https:' + img['uri']
    else:
        img_src = img['uri']
    return img_src


def get_video_info_json(video_id, save_debug=False):
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"110\", \"Not A(Brand\";v=\"24\", \"Microsoft Edge\";v=\"110\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
    }
    video_url = 'https://fave.api.cnn.io/v1/video?id={}&customer=cnn&edition=domestic&env=prod'.format(video_id)
    video_json = utils.get_url_json(video_url, headers=headers)
    if not video_json:
        logger.warning('unable to get video info from ' + video_url)
        return None
    if save_debug:
        utils.write_file(video_json, './debug/video.json')
    return video_json


def process_element(element):
    element_html = ''
    element_contents = None
    if element.get('elementContents'):
        element_contents = element['elementContents']
        if isinstance(element['elementContents'], dict):
            if element['elementContents'].get('type'):
                element_contents = element['elementContents'][element['elementContents']['type']]

    if re.search('article|featured-video-collection|myfinance|read-more', element['contentType']):
        pass

    elif element['contentType'] == 'sourced-paragraph':
        element_html += '<p>'
        if element_contents.get('location') or element_contents.get('source'):
            element_html += '<b>'
        if element_contents.get('location'):
            element_html += element_contents['location']
        if element_contents.get('source'):
            if element_contents.get('location'):
                element_html += '&nbsp;'
            element_html += '({})'.format(element_contents['source'])
        if element_contents.get('location') or element_contents.get('source'):
            element_html += '&nbsp;&ndash;&nbsp;</b>&nbsp;'
        for text in element_contents['formattedText']:
            element_html += text
        element_html += '</p>'

    elif element['contentType'] == 'editorial-note':
        element_html += '<div style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px; font-style:italic;"><b>Editor\'s note:</b> '
        for text in element_contents:
            element_html += text
        element_html += '</div>'

    elif element['contentType'] == 'factbox':
        if not re.search(r'get our free|sign up', element_contents['title'], flags=re.I):
            element_html += '<blockquote><b>{}</b><br>'.format(element_contents['title'])
            for text in element_contents['text']:
                element_html += text['html'][0]
            element_html += '</blockquote>'

    elif element['contentType'] == 'pullquote':
        element_html += '<blockquote><b>{}</b><br> &ndash; {}</blockquote>'.format(element_contents['quote'], element_contents['author'])

    elif element['contentType'] == 'raw-html':
        if re.search(r'\bjs-cnn-erm\b|Click to subscribe|float:left;|float:right;', element_contents['html'], flags=re.I):
            pass
        else:
            raw_soup = BeautifulSoup(element_contents['html'], 'html.parser')
            if raw_soup.video:
                it = raw_soup.find(class_=re.compile(r'cap_\d+'))
                if it:
                    caption = it.get_text()
                else:
                    caption = ''
                element_html += utils.add_video('https:' + raw_soup.source['src'], raw_soup.source['type'], 'https:' + raw_soup.video['poster'], caption)
            else:
                element_html += re.sub(r'(\/\/[^\.]*.cnn\.com)', r'https:\1', element_contents['html'])

    elif element['contentType'] == 'image' or element['contentType'] == 'map':
        img_src = get_resized_image(element_contents['cuts'])
        captions = []
        if element_contents.get('caption'):
            captions.append(element_contents['caption'])
        if element_contents.get('photographer'):
            captions.append(element_contents['photographer'])
        elif element_contents.get('source'):
            captions.append(element_contents['source'])
        element_html += utils.add_image(img_src, ' | '.join(captions))

    elif element['contentType'] == 'gallery-full':
        for content in element_contents:
            if content['contentType'] == 'image':
                img_src = get_resized_image(content['elementContents']['cuts'])
                if content['elementContents'].get('caption'):
                    desc = content['elementContents']['caption'][0]
                else:
                    desc = ''
                if content['elementContents'].get('photographer'):
                    caption = content['elementContents']['photographer']
                elif content['elementContents'].get('source'):
                    caption = content['elementContents']['source']
                else:
                    caption = ''
                element_html += utils.add_image(img_src, caption, desc=desc)

    elif element['contentType'] == 'video-demand':
        video_info = get_video_info_json(element_contents['videoId'])
        if video_info:
            video_src = ''
            for vid in video_info['files']:
                if 'mp4' in vid['bitrate']:
                    video_src = vid['fileUri']
                    video_type = 'video/mp4'
                    break
            if video_src:
                caption = ''
                if video_info.get('headline'):
                    caption += video_info['headline'].strip()
                if video_info.get('description'):
                    if caption and not caption.endswith('.'):
                        caption += '. '
                    caption += video_info['description'].strip()

                for img in reversed(video_info['images']):
                    poster = img['uri']
                    if img['name'] == '640x360':
                        break
                element_html += utils.add_video(video_src, video_type, poster, caption)

    elif element['contentType'] == 'animation':
        video_src = re.sub(r'w_\d+', 'w_640', element['elementContents']['cuts']['medium']['uri'])
        element_html += utils.add_video(video_src, 'video/mp4', video_src.replace('.mp4', '.jpg'))

    elif element['contentType'] == 'youtube':
        if element_contents.get('embedUrl'):
            element_html += utils.add_embed(element_contents['embedUrl'])
        elif element_contents.get('embedHtml'):
            element_html += utils.add_youtube(element_contents['embedHtml'])
        else:
            logger.warning('unhandled contentType youtube')

    elif element['contentType'] == 'instagram':
        if element_contents.get('embedUrl'):
            element_html += utils.add_embed(element_contents['embedUrl'])
        else:
            logger.warning('unhandled contentType instagram')
            #element_html += utils.add_instagram(element_contents['embedHtml'])

    elif element['contentType'] == 'twitter':
        if element_contents.get('embedUrl'):
            element_html += utils.add_embed(element_contents['embedUrl'])
        else:
            m = re.findall(r'(https:\/\/twitter\.com\/[^\/]+\/status/\d+)', element_contents['embedHtml'])
            if m:
                element_html += utils.add_embed(m[-1])
            else:
                logger.warning('unhandled contentType twitter')

    else:
        logger.warning('unhandled contentType ' + element['contentType'])
    return element_html


def format_page_contents(page_contents, item):
    first_element = True
    content_html = ''
    for pages in page_contents:
        for page in pages:
            if page:
                for zone in page['zoneContents']:
                    if isinstance(zone, list):
                        if len(zone) >= 1 and zone[0]:
                            content_html += '<p>'
                            for z in zone:
                                content_html += z
                            content_html += '</p>'
                        continue
                    if zone.get('type'):
                        # Note: "containers" seem to be ads, related articles, etc.
                        if zone['type'] == 'element':
                            # Remove the feed image if there's a lead photo/video
                            if first_element:
                                if re.search(r'^(gallery|image|video)', zone['contentType']):
                                    item['_image'] = item['image']
                                    del item['image']
                            else:
                                if item.get('image'):
                                    content_html += utils.add_image(item['image'])
                                    item['_image'] = item['image']
                                    del item['image']
                            content_html += process_element(zone)
                            first_element = False
                    else:
                        if zone.get('formattedText'):
                            for text in zone['formattedText']:
                                content_html += '<p>{}</p>'.format(text)
    return content_html


def get_item_info(article_json, save_debug=False):
    item = {}
    item['id'] = article_json['sourceId']
    item['url'] = article_json['canonicalUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['firstPublishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['lastPublishDate'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    author = ''
    if isinstance(article_json['bylineProfiles'], list):
        byline_profiles = article_json['bylineProfiles']
    else:
        byline_profiles = article_json['bylineProfiles'][article_json['bylineProfiles']['type']]
    if len(byline_profiles) > 0:
        authors = []
        for byline in byline_profiles:
            authors.append(byline['name'])
        item['author'] = {}
        if authors:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        else:
            item['author']['name'] = 'CNN'
    else:
        item['author'] = {}
        item['author']['name'] = re.sub(r', CNN.*$', '', article_json['bylineText'])

    if article_json.get('metaKeywords'):
        tags = article_json['metaKeywords'].replace(article_json['title'] + ' - CNN', '').strip()
        if tags.endswith(','):
            tags = tags[:-1]
        item['tags'] = [tag.strip() for tag in tags.split(',')]

    item['image'] = 'https:' + article_json['metaImage']
    item['summary'] = article_json['description']
    return item


def get_content(url, args, site_json, save_debug=False):
    url = url.replace('lite.cnn.com', 'www.cnn.com')
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'live-news' in paths or 'spanish' in paths:
        return None
    if split_url.netloc == 'ix.cnn.io' and 'dailygraphics' not in paths:
        return datawrapper.get_content(url, args, site_json, True)

    article_html = utils.get_url_html(url)
    if not article_html:
        return None
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    soup = BeautifulSoup(article_html, 'lxml')

    if split_url.netloc == 'ix.cnn.io' and 'dailygraphics' in paths:
        item = {}
        item['id'] = url
        item['url'] = url
        el = soup.find(id='g-ai2html-graphic-desktop')
        if el:
            m = re.search(r'max-width:(\d+)px;.*max-height:(\d+)px', el['style'])
            item['_image'] = '{}/screenshot?url={}&width={}&height={}&locator=%23g-ai2html-graphic-desktop'.format(config.server, quote_plus(url), m.group(1), m.group(2))
        elif soup.find(id='root'):
            item['_image'] = '{}/screenshot?url={}&locator=%23root&networkidle=true'.format(config.server, quote_plus(url))
        else:
            item['_image'] = '{}/screenshot?url={}'.format(config.server, quote_plus(url))
        item['content_html'] = utils.add_image(item['_image'], link=url)
        return item

    ld_json = []
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json.append(json.loads(el.string))
    if not ld_json:
        logger.warning('unable to find ld+json data in ' + url)
        return None
    if isinstance(ld_json, list) and isinstance(ld_json[0], list):
        ld_json = ld_json[0]
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    if 'podcasts' in paths:
        audio_player = soup.find('audio-player-wc')
        if audio_player:
            item = {}
            item['id'] = url
            item['url'] = url
            el = audio_player.find(id='title')
            if el:
                item['title'] = el.string.encode('iso-8859-1').decode('utf-8')
            el = audio_player.find(id='date')
            if el:
                # Oct 14, 2022
                dt = datetime.strptime(el.string.strip(), '%b %d, %Y')
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt, False)
            el = audio_player.find(id='author')
            if el:
                item['author'] = {}
                item['author']['name'] = el.string
                item['author']['url'] = 'https://www.cnn.com' + el['href']
            el = audio_player.find('picture')
            if el:
                it = el.find('source')
                if it:
                    item['_image'] = 'https://www.cnn.com' + it['srcset']
            el = audio_player.find(id='description')
            if el:
                item['summary'] = el.string.encode('iso-8859-1').decode('utf-8')
            item['_audio'] = utils.get_redirect_url(audio_player['src'])
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/mpeg'
            item['attachments'] = []
            item['attachments'].append(attachment)
            poster = '{}/image?url={}&width=160&overlay=audio'.format(config.server, quote_plus(item['_image']))
            item['content_html'] = '<div style="display:flex; flex-wrap:wrap;">'
            item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><a href="{}"><img style="width:128px;" src="{}"/></a></div>'.format(item['_audio'], poster)
            item['content_html'] += '<div style="flex:2; min-width:256px; margin:auto;">'
            item['content_html'] += '<div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
            item['content_html'] += '<div><a href="{}">{}</a></div>'.format(item['author']['url'], item['author']['name'])
            item['content_html'] += '<div style="font-size:0.8em;">{}&nbsp;&bull;&nbsp;'.format(item['_display_date'])
            el = audio_player.find(id='duration')
            if el:
                item['content_html'] += el.get_text().strip()
            item['content_html'] += '</div></div></div>'
            if 'embed' not in args:
                item['content_html'] += '<p>{}</p>'.format(item['summary'])
            return item
    elif 'videos' in paths:
        article_json = next((it for it in ld_json if it['@type'] == 'VideoObject'), None)
    else:
        article_json = next((it for it in ld_json if it['@type'] == 'NewsArticle'), None)
    if article_json:
        item = {}
        if article_json.get('url'):
            item['url'] = article_json['url']
        elif article_json.get('mainEntityOfPage') and article_json['mainEntityOfPage'].get('url'):
            item['url'] = article_json['mainEntityOfPage']['url']
        else:
            item['url'] = url
        item['id'] = item['url']

        if article_json.get('headline'):
            item['title'] = article_json['headline']
        elif article_json.get('name'):
            item['title'] = article_json['name']

        if article_json.get('datePublished'):
            dt = datetime.fromisoformat(article_json['datePublished'].replace('Z', '+00:00'))
        elif article_json.get('uploadDate'):
            dt = datetime.fromisoformat(article_json['uploadDate'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if article_json.get('dateModified'):
            dt = datetime.fromisoformat(article_json['dateModified'].replace('Z', '+00:00'))
            item['date_modified'] = dt.isoformat()

        item['author'] = {}
        if article_json.get('author'):
            authors = []
            if isinstance(article_json['author'], list):
                for it in article_json['author']:
                    authors.append(it['name'])
                if authors:
                    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
            else:
                item['author']['name'] = re.sub(r'^By\s', '', article_json['author']['name'])
        if not item.get('author') and article_json.get('publisher'):
            item['author']['name'] = article_json['publisher']['name']
        if not item.get('author'):
            item['author']['name'] = 'CNN'

        if article_json.get('articleSection'):
            if isinstance(article_json['articleSection'], list):
                item['tags'] = article_json['articleSection'].copy()

        if article_json.get('image'):
            image = article_json['image']
        elif article_json.get('thumbnail'):
            image = article_json['thumbnail']
        elif article_json.get('thumbnailUrl'):
            image = article_json['thumbnailUrl']
        if isinstance(image, list):
            image = image[0]
        if isinstance(image, dict):
            if image.get('url'):
                item['_image'] = image['url']
            elif image.get('contentUrl'):
                item['_image'] = image['contentUrl']
        else:
            item['_image'] = image

        if article_json.get('description'):
            desc = article_json['description'].replace('&lt;', '<').replace('&gt;', '>')
            item['summary'] = BeautifulSoup('<p>{}</p>'.format(desc), 'html.parser').get_text()

        if article_json.get('@type') == 'VideoObject':
            if article_json['contentUrl'].endswith('.cnn'):
                # https://www.cnn.com/videos/cnn10/2023/02/16/ten-0217orig.cnn
                m = re.search(r'https://www\.cnn\.com/videos/(.*)', article_json['contentUrl'])
                if m:
                    video_json = get_video_info_json(m.group(1), True)
                    if video_json:
                        video = next((it for it in video_json['files'] if (it.get('fileUri') and it['fileUri'].endswith('.mp4'))), None)
                        if video:
                            item['_video'] = video['fileUri']
            else:
                item['_video'] = article_json['contentUrl']
            item['content_html'] = ''
            if item.get('_video'):
                item['content_html'] += utils.add_video(item['_video'], 'video/mp4', item['_image'], 'Watch: ' + item['title'])
            else:
                logger.warning('unknown video content in ' + item['url'])
            if 'embed' in args:
                return item
            item['content_html'] += '<p>{}</p>'.format(item['summary'])
            return item
    else:
        initial_state = None
        el = soup.find('script', string=re.compile(r'window\.__INITIAL_STATE__'))
        if el:
            m = re.search(r'__INITIAL_STATE__ = (.*?);\n', el.string.strip())
            initial_state = json.loads(m.group(1))
            if save_debug:
                utils.write_file(initial_state, './debug/initial.json')
            article_json = initial_state[split_url.path]
        else:
            article_json = utils.get_url_json(utils.clean_url(url) + ':*.json')
        if article_json:
            utils.write_file(article_json, './debug/debug.json')
            item = {}
            item['id'] = article_json['canonicalUrl']
            item['url'] = article_json['canonicalUrl']
            item['title'] = article_json['title']

            dt = datetime.fromisoformat(article_json['firstPublishDate'].replace('Z', '+00:00'))
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            if article_json.get('lastPublishDate'):
                dt = datetime.fromisoformat(article_json['lastPublishDate'].replace('Z', '+00:00'))
                item['date_modified'] = dt.isoformat()

            item['author'] = {}
            if article_json.get('bylineProfiles'):
                if isinstance(article_json['bylineProfiles'], list):
                    byline = article_json['bylineProfiles']
                else:
                    byline = article_json['bylineProfiles'][article_json['bylineProfiles']['type']]
                if len(byline) > 0:
                    authors = []
                    for it in byline:
                        authors.append(it['name'])
                    if authors:
                        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
                    else:
                        item['author']['name'] = 'CNN'
            elif article_json.get('bylineText'):
                item['author']['name'] = re.sub(r', CNN.*$', '', article_json['bylineText'])
            else:
                item['author']['name'] = 'CNN'

            if article_json.get('sectionName'):
                item['tags'] = []
                item['tags'].append(article_json['sectionName'])

            if article_json.get('metaImage'):
                item['image'] = 'https:' + article_json['metaImage']

            if article_json.get('description'):
                item['summary'] = article_json['description']

            if article_json.get('pageContents'):
                item['content_html'] = format_page_contents(article_json['pageContents'], item)

            if initial_state and 'gallery' in paths:
                item['content_html'] = ''
                if item.get('summary'):
                    item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])
                gallery = next((it for it in initial_state.values() if it.get('contentType') and it['contentType'] == 'gallery-full'), None)
                if gallery:
                    item['content_html'] += process_element(gallery)

            item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
            return item
        else:
            meta = {}
            for el in soup.find_all('meta'):
                if el.get('property'):
                    key = el['property']
                elif el.get('name'):
                    key = el['name']
                else:
                    continue
                if meta.get(key):
                    if isinstance(meta[key], str):
                        if meta[key] != el['content']:
                            val = meta[key]
                            meta[key] = []
                            meta[key].append(val)
                    if el['content'] not in meta[key]:
                        meta[key].append(el['content'])
                else:
                    meta[key] = el['content']
            if save_debug:
                utils.write_file(meta, './debug/meta.json')

            item = {}
            item['id'] = meta['og:url']
            item['url'] = meta['og:url']
            item['title'] = meta['og:title']

            dt = datetime.fromisoformat(meta['pubdate'].replace('Z', '+00:00'))
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            if meta.get('lastmod'):
                dt = datetime.fromisoformat(meta['lastmod'].replace('Z', '+00:00'))
                item['date_modified'] = dt.isoformat()

            item['author'] = {}
            if meta.get('author'):
                item['author']['name'] = meta['author']
            elif meta.get('og:site_name'):
                item['author']['name'] = meta['og:site_name']

            if meta.get('section'):
                item['tags'] = []
                item['tags'].append(meta['section'])

            if meta.get('og:image'):
                item['_image'] = meta['og:image']

            if meta.get('description'):
                item['summary'] = meta['description']

    # if 'embed' in args:
    #     if item.get('_image'):
    #         item['content_html'] = utils.add_image(item['_image'], '<a href="{}">{}</a>'.format(item['url'], item['title']), link=item['url'])
    #         return item
    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    if 'gallery' in paths:
        item['content_html'] = ''
        el = soup.find(class_='gallery-inline_unfurled__head')
        if el:
            image = el.find(class_='image')
            if image:
                captions = []
                it = el.find(class_='gallery-inline_unfurled__top--credit')
                if it:
                    captions.append(it.get_text().strip())
                    it.decompose()
                it = el.find(class_='gallery-inline_unfurled__top--caption')
                if it:
                    captions.insert(0, it.get_text().strip())
                item['content_html'] += utils.add_image(resize_image(image['data-url']), ' | '.join(captions))
        el = soup.find(class_='gallery-inline_unfurled__description')
        if el:
            item['content_html'] += el.decode_contents()
        el = soup.find(class_='gallery-inline_unfurled__slides-unfurled')
        if el:
            for image in el.find_all(class_='image'):
                it = image.find(class_='image__credit')
                if it:
                    caption = it.get_text().strip()
                else:
                    caption = ''
                it = image.find(attrs={"data-editable": "metaCaption"})
                if it:
                    it.name = 'p'
                    desc = str(it)
                else:
                    desc = ''
                item['content_html'] += utils.add_image(image['data-url'], caption, desc=desc)
        return item

    gallery = None
    content = soup.find(class_='article__content')
    if content:
        lede = ''
        el = soup.find(class_='image__lede')
        if el:
            div = el.find(class_='video-resource')
            if div:
                if article_json.get('video'):
                    video = None
                    for it in article_json['video']:
                        if it.get('url') and re.search(div['data-video-id'], it['url']):
                            video = it
                            break
                        elif it.get('embedUrl') and re.search(div['data-video-id'], it['embedUrl']):
                            video = it
                            break
                    #video = next((it for it in article_json['video'] if re.search(div['data-video-id'], it['url'])), None)
                    if video:
                        image = json.loads(html.unescape(div['data-fave-thumbnails']))
                        captions = []
                        if div.get('data-headline'):
                            captions.append(html.unescape(div['data-headline']))
                        if div.get('data-source-html'):
                            source = BeautifulSoup(html.unescape(div['data-source-html']),
                                                   'html.parser').get_text().strip()
                            captions.append(re.sub(r'^-\s*', '', source))
                        lede += utils.add_video(video['contentUrl'], 'video/mp4', image['big']['uri'], 'Watch: ' + ' | '.join(captions))
            if not lede:
                div = el.find(class_='interactive-video')
                if div:
                    video = div.find('video')
                    if video:
                        lede += utils.add_video(video.source['src'], video.source['type'], video.get('poster'))
            if not lede:
                gallery = el.find(class_='gallery-inline')
                if gallery:
                    div = el.find(class_='image_gallery-image')
                    if div:
                        captions = []
                        it = div.find(class_='image_gallery-image__credit')
                        if it and it.get_text().strip():
                            captions.append(it.get_text().strip())
                            it.decompose()
                        it = div.find(class_='image_gallery-image__caption')
                        if it and it.get_text().strip():
                            captions.insert(0, it.get_text().strip())
                        if gallery.get('data-headline'):
                            caption = '<b>{}</b> (gallery below)<br/>'.format(gallery['data-headline'])
                        else:
                            caption = '<b>Photo gallery</b> (below)<br/>'
                        caption += ' | '.join(captions)
                        lede += utils.add_image(div['data-url'], caption)
            if not lede:
                div = el.find(class_='image')
                if div:
                    captions = []
                    it = el.find(class_='image__credit')
                    if it and it.get_text().strip():
                        captions.append(it.get_text().strip())
                        it.decompose()
                    it = el.find(class_='image__caption')
                    if it and it.get_text().strip():
                        captions.insert(0, it.get_text().strip())
                    lede += utils.add_image(div['data-url'], ' | '.join(captions))
        item['content_html'] = lede
        source = ''
        for el in content.find_all(recursive=False):
            new_html = ''
            if 'paragraph' in el['class'] or 'subheader' in el['class']:
                el.attrs = {}
                if source:
                    el.insert(0, BeautifulSoup(source, 'html.parser'))
                    source = ''
                continue
            elif 'image' in el['class'] or 'image_inline-small' in el['class']:
                captions = []
                it = el.find(class_=re.compile(r'^image_.*_credit$'))
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                    it.decompose()
                it = el.find(attrs={"itemprop": "caption"})
                if it and it.get_text().strip():
                    captions.insert(0, it.get_text().strip())
                new_html = utils.add_image(resize_image(el['data-url']), ' | '.join(captions))
            elif 'image-slider' in el['class']:
                captions = []
                it = el.find(class_=re.compile(r'^image_.*_credit$'))
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                    it.decompose()
                it = el.find(attrs={"itemprop": "caption"})
                if it and it.get_text().strip():
                    captions.insert(0, it.get_text().strip())
                new_html = '<figure style="margin:0; padding:0;"><div style="display:flex; flex-wrap:wrap;">'
                for it in el.find_all(class_='image'):
                    new_html += '<div style="flex:1; min-width:360px;"><img src="{}" style="width:100%;" /></div>'.format(resize_image(it['data-url']))
                new_html += '</div>'
                if captions:
                    new_html += '<figcaption><small>{}</small></figcaption>'.format(' | '.join(captions))
                new_html += '</figure>'
            elif 'gallery-inline' in el['class']:
                gallery = copy.copy(el)
                div = el.find(class_='image_gallery-image')
                if div:
                    captions = []
                    it = div.find(class_='image_gallery-image__credit')
                    if it and it.get_text().strip():
                        captions.append(it.get_text().strip())
                        it.decompose()
                    it = div.find(class_='image_gallery-image__caption')
                    if it and it.get_text().strip():
                        captions.insert(0, it.get_text().strip())
                    if el.get('data-headline'):
                        caption = '<b>{}</b> (gallery below)<br/>'.format(el['data-headline'])
                    else:
                        caption = '<b>Photo gallery</b> (below)<br/>'
                    caption += ' | '.join(captions)
                    new_html = utils.add_image(div['data-url'], caption)
            elif 'interactive-video' in el['class']:
                video = el.find('video')
                if video:
                    new_html = utils.add_video(video.source['src'], video.source['type'], video.get('poster'))
            elif 'video-resource' in el['class']:
                video = None
                for it in article_json['video']:
                    if it.get('url') and re.search(el['data-video-id'], it['url']):
                        video = it
                        break
                    elif it.get('embedUrl') and re.search(el['data-video-id'], it['embedUrl']):
                        video = it
                        break
                #video = next((it for it in article_json['video'] if re.search(el['data-video-id'], it['url'])), None)
                if video:
                    image = json.loads(html.unescape(el['data-fave-thumbnails']))
                    captions = []
                    if el.get('data-headline'):
                        captions.append(html.unescape(el['data-headline']))
                    if el.get('data-source-html'):
                        source = BeautifulSoup(html.unescape(el['data-source-html']), 'html.parser').get_text().strip()
                        captions.append(re.sub(r'^-\s*', '', source))
                        source = ''
                    new_html = utils.add_video(video['contentUrl'], 'video/mp4', image['big']['uri'], 'Watch: ' + ' | '.join(captions))
            elif 'youtube' in el['class']:
                it = el.find(class_='youtube__content')
                if it:
                    new_html = utils.add_embed('https://www.youtube.com/embed/' + it['data-video-id'])
            elif 'twitter' in el['class']:
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif 'instagram' in el['class']:
                it = el.find(attrs={"data-instgrm-permalink": True})
                if it:
                    new_html = utils.add_embed(it['data-instgrm-permalink'])
            elif 'map' in el['class']:
                new_html = utils.add_image('{}/screenshot?url={}&locator={}'.format(config.server, quote_plus(item['url']), quote_plus('[data-id="{}"]'.format(el['data-id']))))
            elif 'graphic' in el['class']:
                it = el.find(class_='graphic__anchor')
                if it:
                    new_html = utils.add_embed(it['data-url'])
            elif 'html-embed' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
                else:
                    it = el.find(attrs={"data-type": "dailygraphics"})
                    if it:
                        new_html = utils.add_image('{}/screenshot?url={}&locator=%23root'.format(config.server, quote_plus(it['data-url'])), link=it['data-url'])
                    else:
                        it = el.find(class_='cnn-pcl-embed')
                        if it:
                            new_item = None
                            if it.get('data-href'):
                                new_item = get_content(it['data-href'], ['embed'], site_json, False)
                            elif it.get('data-click-through'):
                                new_item = get_content(it['data-click-through'], ['embed'], site_json, False)
                            if new_item:
                                new_html = new_item['content_html']
                if not new_html:
                    div = el.find(class_=re.compile(r'^m-infographic'))
                    if div:
                        if el.style and not next((it for it in div.contents if it != '\n'), None):
                            m = re.findall(r'background-image:\s*url\(([^\)]+)\)', el.style.string)
                            if m:
                                img_src = m[-1]
                                if img_src.startswith('//'):
                                    img_src = 'https:' + img_src
                                elif img_src.startswith('/'):
                                    img_src = 'https://www.cnn.com' + img_src
                                h = re.search(r'height:([^;]+);', el.style.string)
                                if h:
                                    new_html = '<div style="width:100%; text-align:center;"><img src="{}" style="width:{};" /></div>'.format(img_src, h.group(1))
                                else:
                                    new_html = utils.add_image(img_src)
                        elif div.get('id') and div['id'] == 'ck-st-video-wt':
                            video = div.find('video', class_='ck-vid-desk')
                            if video:
                                caption = ''
                                if el:
                                    caption = '<b>Interactive content:</b> '
                                    m = re.search(r'document\.location\.href\s?=\s?"([^"]+)"', el.script.string)
                                    if m:
                                        link = m.group(1)
                                    else:
                                        link = ''
                                    m = re.search(r'interaction:\s?"([^"]+)"', el.script.string)
                                    if m:
                                        if link:
                                            caption += '<a href="{}">{}</a>'.format(link, m.group(1))
                                        else:
                                            caption += m.group(1)
                                new_html = utils.add_video(video.source['src'], video.source['type'], video['poster'], caption)
                        elif div.find(class_='cnnix-tout'):
                            link = div.find('a')
                            new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            it = div.find('img')
                            if it:
                                new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><a href="{}"><img style="width:100%;" src="{}"/></a></div>'.format(link['href'], it['src'])
                            it = div.find('p')
                            if it:
                                new_html += '<div style="flex:2; min-width:256px; margin:auto; font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(link['href'], it.get_text())
                            new_html += '</div>'
                        elif div.find(class_='v-photo-container'):
                            new_html = '<figure style="margin:0; padding:0;"><div style="display:flex; flex-wrap:wrap; gap:1em;">'
                            for it in div.find_all(class_='v-photo-container'):
                                image = it.find('img')
                                if image:
                                    new_html += '<div style="flex:1; min-width:256px;"><img style="width:100%;" src="{}"/>'.format(image['src'])
                                    caption = it.find(class_='v-photo-caption')
                                    if caption:
                                        new_html += '<div><small>{}</small></div>'.format(caption.get_text().strip())
                                    new_html += '</div>'
                            new_html += '</div></figure>'
                        else:
                            it = div.find(id=True)
                            if it and div.script:
                                m = re.search(r'pym\.Parent\("{}","([^"]+)"'.format(it['id']), div.script.string)
                                if m:
                                    new_item = get_content('https:' + m.group(1), args, site_json, False)
                                    if new_item:
                                        new_html = new_item['content_html']
            elif 'source' in el['class']:
                source = '<b>'
                it = el.find(class_='source__location')
                if it and it.get_text().strip():
                    source += '{} '.format(it.get_text().strip())
                it = el.find(class_='source__text')
                if it and it.get_text().strip():
                    source += '({}) — '.format(it.get_text().strip())
                source += '</b>'
                el.decompose()
                continue
            elif 'list' in el['class']:
                el.unwrap()
                continue
            elif 'pull-quote' in el['class']:
                it = el.find(class_='pull-quote__text')
                if it and it.get_text().strip():
                    quote = it.get_text().strip()
                else:
                    quote = ''
                it = el.find(class_='pull-quote__attribution')
                if it and it.get_text().strip():
                    author = it.get_text().strip()
                else:
                    author = ''
                if quote:
                    new_html = utils.add_pullquote(quote, author)
            elif 'highlights' in el['class']:
                new_html = utils.add_blockquote(el.decode_contents())
            elif 'editor-note' in el['class'] or 'correction' in el['class']:
                el.attrs = {}
                el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px; font-style:italic;'
                continue
            elif 'footnote' in el['class']:
                el.attrs = {}
                el['style'] = 'font-style:italic;'
                continue
            elif 'factbox_inline-small' in el['class']:
                it = el.find(attrs={"data-editable": "title"})
                if it:
                    if re.search(r'^Latest|^More on|newsletter', it.get_text().strip(), flags=re.I):
                        el.decompose()
                        continue
                    else:
                        new_html = utils.add_blockquote(el.decode_contents())
            elif 'related-content' in el['class'] or 'related-content_full-width' in el['class'] or 'related-content_without-image' in el['class']:
                el.decompose()
                continue
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled content element {} in {}'.format(el['class'], item['url']))
    else:
        content = soup.find(class_=['Article__body', 'BasicArticle__main', 'SpecialArticle__body'])
        if content:
            item['content_html'] = ''
            el = soup.find(class_='SpecialArticle__headDescription')
            if el:
                item['content_html'] += '<p><em>{}</em></p>'.format(el.get_text().strip())

            el = soup.find(class_=['Hero__imageWrapper', 'BasicArticle__hero', 'SpecialArticle__hero'])
            if el:
                it = el.find('img', class_='Image__image')
                if it:
                    img_src = resize_image(it['src'])
                else:
                    img_src = ''
                captions = []
                it = el.find(class_=re.compile(r'__heroCredit'))
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                    it.decompose()
                it = el.find(class_=re.compile('__heroCaption'))
                if it and it.get_text().strip():
                    captions.insert(0, it.get_text().strip())
                if img_src:
                    item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

            for el in content.find_all(class_=False, recursive=False):
                # This seems to be malformed html
                el.unwrap()
            for el in content.find_all(recursive=False):
                new_html = ''
                if re.search(r'Paragraph__|__paragraph', ' '.join(el['class'])):
                    # TODO: __isDropCap
                    it = el.find('cite')
                    if it:
                        it.name = 'strong'
                    it = el.find('span', recursive=False)
                    if it:
                        it.unwrap()
                    el.name = 'p'
                    if 'Paragraph__isEditorialNote' in el['class']:
                        el.attrs = {}
                        el['style'] = 'border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px; font-style:italic;'
                        el.insert(0, BeautifulSoup('<b>Editor\'s note: </b>', 'html.parser'))
                    else:
                        el.attrs = {}
                    continue
                elif 'EditorialNote__component' in el['class']:
                    el.attrs = {}
                    el['style'] = 'border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px; font-style:italic;'
                    continue
                elif 'BasicArticle__image' in el['class'] or 'CaptionedImage__component' in el['class'] or ('SpecialArticle__padLarge' in el['class'] and el.find('img', class_='Image__image')):
                    it = el.find('img', class_='Image__image')
                    img_src = resize_image(it['src'])
                    captions = []
                    credit = ''
                    for it in el.find_all(class_=re.compile(r'__credit')):
                        credit += it.get_text()
                        it.decompose()
                    if credit.strip():
                        captions.append(credit.strip())
                    it = el.find(class_=re.compile(r'__caption'))
                    if it and it.get_text().strip():
                        captions.insert(0, it.get_text().strip())
                    if img_src:
                        new_html = utils.add_image(img_src, ' | '.join(captions))
                elif re.search(r'__pullquote', ' '.join(el['class'])):
                    it = el.find(class_=re.compile(r'__pullquoteText'))
                    if it and it.get_text().strip():
                        quote = it.get_text().strip()
                    else:
                        quote = ''
                    it = el.find(class_=re.compile(r'__pullquoteAuthor'))
                    if it and it.get_text().strip():
                        author = it.get_text().strip()
                    else:
                        author = ''
                    if quote:
                        new_html = utils.add_pullquote(quote, author)
                elif re.search(r'Ad__|__ad|RelatedArticle|__related|SocialBar|Authors__component', ' '.join(el['class'])):
                    el.decompose()
                    continue
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled content element {} in {}'.format(el['class'], item['url']))
        else:
            logger.warning('unknown article content in ' + item['url'])
            return None

    item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', content.decode_contents())

    if gallery:
        if gallery.get('data-headline'):
            item['content_html'] += '<h3>{}</h3>'.format(gallery['data-headline'])
        else:
            item['content_html'] += '<h3>Image gallery</h3>'
        for el in gallery.find_all(class_='image_gallery-image'):
            captions = []
            it = el.find(class_='image_gallery-image__credit')
            if it and it.get_text().strip():
                captions.append(it.get_text().strip())
                it.decompose()
            it = el.find(class_='image_gallery-image__caption')
            if it and it.get_text().strip():
                captions.insert(0, it.get_text().strip())
            item['content_html'] += utils.add_image(el['data-url'], ' | '.join(captions)) + '<div>&nbsp;</div>'
        gallery.decompose()
    return item


def get_live_news_content(url, args, site_json, save_debug=False):
    livestory_id = url.split('/')[-1]
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"90\", \"Google Chrome\";v=\"90\"",
        "sec-ch-ua-mobile": "?0",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "sec-gpc": "1",
        "x-api-key": "P7LEOCujzt2RqSaWBeImz1spIoLq7dep7x983yQc",
        "x-graphql-query-uuid": "livestory---PostsWithGraph{\"livestory_id\":\"h_dd3c2644be053a63af6b1bf86dc61ba8\",\"startId\":null}---0d02c8bfc7cb62ae01f7de7f444069bfda2614c90952730601e1f22df0641fe1"
    }
    gql_query = '{\"operationName\":\"PostsWithGraph\",\"variables\":{\"livestory_id\":\"h_dd3c2644be053a63af6b1bf86dc61ba8\",\"startId\":null},\"query\":\"query PostsWithGraph($livestory_id: String) {\\n  getLivestoryWebData(livestory_id: $livestory_id) {\\n    id\\n    lastPublishDate\\n    lastPublishDateFormatted\\n    activityStatus\\n    pinnedPosts {\\n      id\\n      lastPublishDate\\n      __typename\\n    }\\n    unpinnedPosts {\\n      id\\n      sourceId\\n      lastPublishDate\\n      lastPublishDateFormatted\\n      headline\\n      byline\\n      content\\n      tags\\n      __typename\\n    }\\n    tags\\n    __typename\\n  }\\n}\\n\"}'

    livestory_json = utils.post_url('https://data.api.cnn.io/graphql', gql_query, headers)
    if save_debug:
        with open('./debug/debug.json', 'w') as file:
            json.dump(livestory_json, file, indent=4)
    return None


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.rss'):
        # https://www.cnn.com/services/rss/
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')

    feed_urls = []
    for el in soup.find_all('a', class_='container__link'):
        if el['href'] not in feed_urls:
            feed_urls.append(el['href'])

    if not feed_urls:
        for el in soup.find_all(class_='cd__headline'):
            if el.a['href'] not in feed_urls:
                feed_urls.append(el.a['href'])

    if not feed_urls:
        for el in soup.find_all('link', href=re.compile(r'coverageContainer')):
            container_html = utils.get_url_html('https://www.cnn.com' + el['href'])
            if container_html:
                container_soup = BeautifulSoup(container_html, 'html.parser')
                for it in container_soup.find_all('a'):
                    if it['href'] not in feed_urls:
                        feed_urls.append(it['href'])

    n = 0
    feed_items = []
    for article_url in feed_urls:
        if save_debug:
            logger.debug('getting content for https://www.cnn.com' + article_url)
        item = get_content('https://www.cnn.com' + article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed