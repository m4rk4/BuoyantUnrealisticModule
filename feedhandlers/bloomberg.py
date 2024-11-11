import json, math, re
from bs4 import BeautifulSoup
from curl_cffi import requests
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)

def resize_image(img_src):
    return re.sub(r'[\d-]+x[\d-]+.(jpg|png)', '1200x-1.\\1', img_src)


def get_bb_url(url, get_json=False):
    # print(url)
    r = requests.get(url, impersonate=config.impersonate)
    if r.status_code != 200:
        return None
    if get_json:
        return r.json()
    return r.text
    # headers = {
    #     "accept-encoding": "gzip, deflate, br",
    #     "accept-language": "en-US,en;q=0.9,de;q=0.8",
    #     "cache-control": "max-age=0",
    #     "sec-ch-ua": "\"Chromium\";v=\"106\", \"Microsoft Edge\";v=\"106\", \"Not;A=Brand\";v=\"99\"",
    #     "sec-ch-ua-mobile": "?0",
    #     "sec-ch-ua-platform": "\"Windows\"",
    #     "sec-fetch-dest": "document",
    #     "sec-fetch-mode": "navigate",
    #     "sec-fetch-site": "none",
    #     "sec-fetch-user": "?1",
    #     "sec-gpc": "1",
    #     "upgrade-insecure-requests": "1",
    #     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.47"
    # }
    # if get_json:
    #     headers['accept'] = 'application/json'
    #     content = utils.get_url_json(url, headers=headers, allow_redirects=False)
    # else:
    #     headers['accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9'
    #     content = utils.get_url_html(url, headers=headers, allow_redirects=False)
    #     if not content:
    #         content = utils.get_url_html('https://webcache.googleusercontent.com/search?q=cache:' + utils.clean_url(url), headers=headers, allow_redirects=False)
    # if not content:
    #     # Try through browser
    #     try:
    #         content = utils.get_browser_request(url, get_json)
    #     except:
    #         logger.warning('get_browser_request exception for ' + url)
    #         return None
    # return content


def add_video(video_id):
    #api_url = 'https://www.bloomberg.com/multimedia/api/embed?id=' + video_id
    api_url = 'https://www.bloomberg.com/media-manifest/embed?id=' + video_id
    video_json = get_bb_url(api_url, True)
    if video_json:
        caption = 'Watch: '
        if video_json.get('title'):
            caption += video_json['title']
        elif video_json.get('description'):
            caption += video_json['description']
        poster = resize_image('https:' + video_json['thumbnail']['baseUrl'])
        return utils.add_video(video_json['downloadURLs']['600'], 'video/mp4', poster, caption)
    else:
        logger.warning('error getting video json ' + api_url)
        return ''


def format_content(content, images):
    content_html = ''
    if content['type'] == 'ad' or content['type'] == 'inline-newsletter':
        pass
    elif content['type'] == 'text':
        start_tag = ''
        end_tag = ''
        if content.get('attributes'):
            for key in content['attributes'].keys():
                if key == 'strong':
                    start_tag += '<strong>'
                    end_tag = '</strong>' + end_tag
                elif key == 'emphasis':
                    start_tag += '<em>'
                    end_tag = '</em>' + end_tag
                else:
                    logger.warning('unhandled text attribute ' + key)
        content_html += start_tag + content['value'] + end_tag
    elif content['type'] == 'br':
        content_html += '<br/>'
    elif content['type'] == 'paragraph':
        content_html += '<p>'
        for c in content['content']:
            content_html += format_content(c, images)
        content_html += '</p>'
    elif content['type'] == 'link':
        link = ''
        if content['data']['destination'].get('web'):
           link = content['data']['destination']['web']
        elif content['data']['destination'].get('bbg'):
            if content['data']['destination']['bbg'].startswith('bbg://people/'):
                pass
            elif content['data']['destination']['bbg'].startswith('bbg://msg/'):
                link = content['data']['destination']['bbg'].replace('bbg://msg/', '')
            elif content['data']['destination']['bbg'].startswith('bbg://securities/'):
                keys = unquote_plus(content['data']['destination']['bbg']).split('/')[3].split(' ')
                if 'Equity' in keys:
                    keys.remove('Equity')
                    link = 'https://www.bloomberg.com/quote/' + ':'.join(keys)
                elif 'USGG30YR' in keys:
                    link = 'https://www.bloomberg.com/markets/rates-bonds/government-bonds/us'
                else:
                    logger.warning('unhandled bbg link ' + content['data']['destination']['bbg'])
                    link = content['data']['destination']['bbg']
            elif content['data']['destination']['bbg'].startswith('bbg://screens/wcrs'):
                link = 'https://www.bloomberg.com/markets/currencies'
            else:
                logger.warning('unhandled bbg link ' + content['data']['destination']['bbg'])
                link = content['data']['destination']['bbg']
        if link:
            content_html += '<a href="{}">'.format(link)
        for c in content['content']:
            content_html += format_content(c, images)
        if link:
            content_html += '</a>'
    elif content['type'] == 'entity':
        if content['subType'] == 'story' and content['meta']['type'] == 'StoryLink':
            if content['data']['link']['destination'].get('web'):
                content_html += '<a href="{}">'.format(content['data']['link']['destination']['web'])
            for c in content['content']:
                content_html += format_content(c, images)
            content_html += '</a>'
        elif content['subType'] == 'security' and content['meta']['type'] == 'SecurityLink':
            keys = unquote_plus(content['data']['link']['destination']['bbg']).split('/')[3].split(' ')
            if 'Equity' in keys:
                keys.remove('Equity')
                link = 'https://www.bloomberg.com/quote/' + ':'.join(keys)
                content_html += '<a href="{}">'.format(link)
                for c in content['content']:
                    content_html += format_content(c, images)
                content_html += '</a>'
            else:
                logger.warning('unhandled entity security bbg link ' + content['data']['link']['destination']['bbg'])
        elif content['subType'] == 'person' and content['meta']['type'] == 'ProfileLink':
            # TODO
            for c in content['content']:
                content_html += format_content(c, images)
        else:
            logger.warning('unhandled content entity type ' + content['subType'])
            for c in content['content']:
                content_html += format_content(c, images)
    elif content['type'] == 'heading':
        content_html += '<h{}>'.format(content['data']['level'])
        for c in content['content']:
            content_html += format_content(c, images)
        content_html += '</h{}>'.format(content['data']['level'])
    elif content['type'] == 'list':
        if content['subType'] == 'unordered':
            content_html += '<ul>'
        else:
            content_html += '<ol>'
        for c in content['content']:
            content_html += format_content(c, images)
        if content['subType'] == 'unordered':
            content_html += '</ul>'
        else:
            content_html += '</ol>'
    elif content['type'] == 'listItem':
        content_html += '<li>'
        for c in content['content']:
            content_html += format_content(c, images)
        content_html += '</li>'
    elif content['type'] == 'media':
        if content['subType'] == 'photo' or content['subType'] == 'chart':
            if content['data'].get('attachment') and images.get(content['data']['attachment']['id']):
                image = images[content['data']['attachment']['id']]
                captions = []
                if image.get('caption'):
                    captions.append(image['caption'])
                elif image.get('title'):
                    captions.append(image['title'])
                if image.get('credit'):
                    captions.append(image['credit'])
                caption = re.sub(r'<p>|</p>', '', ' | '.join(captions))
                content_html += utils.add_image(resize_image(image['url']), caption)
            else:
                captions = []
                if content['data'][content['subType']].get('caption'):
                    captions.append(content['data'][content['subType']]['caption'])
                if content['data'][content['subType']].get('credit'):
                    captions.append(content['data'][content['subType']]['credit'])
                caption = re.sub(r'<p>|</p>', '', ' | '.join(captions))
                if content['subType'] == 'chart':
                    content_html += utils.add_image(content['data']['chart']['fallback'], caption)
                else:
                    content_html += utils.add_image(content['data']['photo']['src'], caption)
        elif content['subType'] == 'video':
            # content_html += add_video(content['data']['attachment']['id'])
            caption = 'Watch: {}'.format(content['data']['attachment']['title'])
            poster = resize_image(content['data']['attachment']['thumbnail']['url'])
            content_html += utils.add_video(content['data']['attachment']['streams'][0]['url'], content['data']['attachment']['streams'][0]['type'], poster, caption)
        elif content['subType'] == 'audio':
            if content['data']['attachment'].get('image'):
                poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(content['data']['attachment']['image']['url']))
            else:
                poster = '{}/static/play_button-48x48.png'.format(config.server)
            content_html += '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td>'.format(content['data']['attachment']['url'], poster)
            content_html += '<td style="vertical-align:top;"><div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(content['data']['attachment']['url'], content['data']['attachment']['title'])
            if content['data']['attachment'].get('description'):
                content_html += '<div style="font-size:0.9em;">{}</div>'.format(content['data']['attachment']['description'])
            if content['data']['attachment'].get('duration'):
                s = float(int(content['data']['attachment']['duration']) / 1000)
                h = math.floor(s / 3600)
                s = s - h * 3600
                m = math.floor(s / 60)
                s = s - m * 60
                if h > 0:
                    duration = '{:0.0f}:{:02.0f}:{:02.0f}'.format(h, m, s)
                else:
                    duration = '{:0.0f}:{:02.0f}'.format(m, s)
                content_html += '<div style="font-size:0.9em;">{}</div>'.format(duration)
            content_html += '</td></tr></table>'
        elif content['subType'] == 'embed':
            content_html += utils.add_embed(content['href'])
        else:
            logger.warning('unhandled content media subtype ' + content['subType'])
    elif content['type'] == 'embed':
        if content.get('href'):
            content_html += utils.add_embed(content['href'])
        else:
            logger.warning('unhandled embed content')
    elif content['type'] == 'quote':
        # Blockquote or pullquote?
        quote = ''
        for c in content['content']:
            quote += format_content(c, images)
        content_html += utils.add_blockquote(quote)
    elif content['type'] == 'aside':
        if content['data'].get('class') and content['data']['class'] == 'pullquote':
            quote = ''
            for c in content['content']:
                quote += format_content(c, images)
            content_html += utils.add_pullquote(quote)
        else:
            logger.warning('unhandled aside content')
    elif content['type'] == 'footnoteRef':
        m = re.search(r'footnote-(\d+)', content['data']['identifier'])
        if m:
            content_html += '[{}]'.format(m.group(1))
        else:
            logger.warning('unhandled footnoteRef content')
    elif content['type'] == 'footnotes':
        for c in content['content']:
            content_html += format_content(c, images)
    elif content['type'] == 'footnote':
        footnote = ''
        for c in content['content']:
            footnote += format_content(c, images)
        m = re.search(r'footnote-(\d+)', content['data']['identifier'])
        if m:
            content_html += re.sub('^<p>', '<p>[{}] '.format(m.group(1)), footnote)
        else:
            logger.warning('unhandled footnote content')
    elif content['type'] == 'inline-recirc':
        pass
    else:
        logger.warning('unhandled content type ' + content['type'])
    return content_html


def get_video_content(url, args, site_json, save_debug):
    if args and 'embed' in args:
        video_id = url
        bb_json = None
    else:
        bb_html = get_bb_url(url)
        if not bb_html:
            return None
        if save_debug:
            utils.write_file(bb_html, './debug/debug.html')

        m = re.search(r'window\.__PRELOADED_STATE__ = ({.+});', bb_html)
        if not m:
            logger.warning('unable to parse __PRELOADED_STATE__ in ' + url)
            return None
        bb_json = json.loads(m.group(1))
        if save_debug:
            utils.write_file(bb_json, './debug/debug.json')
        video_id = bb_json['quicktakeVideo']['videoStory']['video']['bmmrId']

    video_json = get_bb_url('https://www.bloomberg.com/multimedia/api/embed?id=' + video_id, True)
    if not video_json:
        return None
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    item = {}
    if bb_json:
        item['id'] = bb_json['quicktakeVideo']['videoStory']['id']
        item['url'] = bb_json['quicktakeVideo']['videoStory']['url']
    else:
        item['id'] = video_json['id']
        item['url'] = video_json['downloadURLs']['600']

    item['title'] = video_json['title']

    dt = datetime.fromtimestamp(int(video_json['createdUnixUTC'])).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    if video_json.get('peopleCodes'):
        authors = []
        for key, val in video_json['peopleCodes'].items():
            authors.append(val.title())
        if authors:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    if not item['author'].get('name'):
        item['author']['name'] = 'Bloomberg News'

    if video_json.get('metadata') and video_json['metadata'].get('contentTags'):
        item['tags'] = []
        for tag in video_json['metadata']['contentTags']:
            item['tags'].append(tag['id'])

    item['_image'] = resize_image('https:' + video_json['thumbnail']['baseUrl'])
    item['_video'] = video_json['downloadURLs']['600']
    item['_audio'] = video_json['audioMp3Url']

    item['summary'] = video_json['description']

    if args and 'embed' in args:
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'], video_json['description'])
    else:
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'])
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
        if bb_json['quicktakeVideo']['videoStory']['video'].get('transcript'):
            item['content_html'] += '<h3>Transcript</h3><p>{}</p>'.format(
                bb_json['quicktakeVideo']['videoStory']['video']['transcript'].replace('\n', ''))
    return item


def get_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'videos' in paths:
        return get_video_content(url, args, site_json, save_debug)

    page_html = get_bb_url(url)
    if page_html:
        if save_debug:
            utils.write_file(page_html, './debug/debug.html')
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if save_debug:
                utils.write_file(next_data, './debug/next.json')
            return get_item(next_data['props']['pageProps']['story'], args, site_json, save_debug)

    logger.debug('unable to get __NEXT_DATA__ for ' + url)

    api_url = ''
    m = re.search(r'\/(news|opinion)\/articles\/(.*)', split_url.path)
    if m:
        api_url = 'https://www.bloomberg.com/javelin/api/foundation_transporter/' + m.group(2)
    else:
        m = re.search(r'\/(news|politics)\/features\/(.*)', split_url.path)
        if m:
            api_url = 'https://www.bloomberg.com/javelin/api/foundation_feature_transporter/' + m.group(2)
    if not api_url:
        logger.warning('unsupported url ' + url)
        return None

    api_json = get_bb_url(api_url, True)
    if not api_json:
        return None
    # if save_debug:
    #     utils.write_file(api_json, './debug/content.json')
    soup = BeautifulSoup(api_json['html'], 'html.parser')
    el = soup.find('script', attrs={"data-component-props": re.compile(r'ArticleBody|FeatureBody')})
    if el:
        article_json = json.loads(el.string)
        return get_item(article_json['story'], args, site_json, save_debug)

    logger.warning('unable to get content for ' + url)
    return None


def get_item(story_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')

    item = {}
    item['id'] = story_json['id']
    if story_json.get('canonical'):
        item['url'] = story_json['canonical']
    elif story_json.get('seoCanonical'):
        item['url'] = story_json['seoCanonical']
    elif story_json.get('url'):
        item['url'] = story_json['url']

    if story_json.get('textHeadline'):
        item['title'] = story_json['textHeadline']
    elif story_json.get('headline'):
        item['title'] = story_json['headline']

    dt = datetime.fromisoformat(story_json['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(story_json['updatedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    item['author'] = {}
    if story_json.get('authors'):
        authors = []
        for author in story_json['authors']:
            authors.append(author['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif story_json.get('byline'):
        item['author']['name'] = story_json['byline']

    if story_json.get('mostRelevantTags'):
        item['tags'] = story_json['mostRelevantTags'].copy()

    if story_json.get('teaserBody'):
        item['summary'] = story_json['teaserBody']
    elif story_json.get('summary'):
        item['summary'] = story_json['summary']
    elif story_json.get('summaryHtml'):
        item['summary'] = story_json['summaryHtml']
    elif story_json.get('summaryText'):
        item['summary'] = story_json['summaryText']
    elif story_json.get('socialDescription'):
        item['summary'] = story_json['socialDescription']
    if item.get('summary') and item['summary'].startswith('<p>'):
        item['summary'] = re.sub(r'^<p>(.*)</p>$', r'\1', item['summary']).replace('</p><p>', '<br/><br/>')

    item['content_html'] = ''

    # el = soup.find('ul', class_='abstract-v2')
    # if el:
    #  item['content_html'] += str(el)

    if story_json.get('dek'):
        item['content_html'] += story_json['dek']
    elif item.get('summary'):
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    if story_json.get('abstract'):
        item['content_html'] += '<ul>'
        for it in story_json['abstract']:
            item['content_html'] += '<li>{}</li>'.format(it)
        item['content_html'] += '</ul>'

    if isinstance(story_json['body'], str):
        body = BeautifulSoup(story_json['body'], 'html.parser')
    else:
        body = None

    lede = ''
    if story_json.get('lede'):
        if story_json['lede']['type'] == 'image':
            item['_image'] = story_json['ledeImageUrl']
            captions = []
            if story_json['lede'].get('caption'):
                captions.append(story_json['lede']['caption'])
            if story_json['lede'].get('credit'):
                captions.append(story_json['lede']['credit'])
            caption = re.sub(r'<p>|</p>', '', ' | '.join(captions))
            lede += utils.add_image(resize_image(story_json['ledeImageUrl']), caption)
        elif story_json['lede']['type'] == 'video':
            video = None
            if story_json.get('videoAttachments'):
                for key, val in story_json['videoAttachments'].items():
                    if val.get('id') == story_json['lede']['id']:
                        video = val
                        break
            if video:
                caption = 'Watch: {}'.format(video['title'])
                poster = resize_image(video['thumbnail']['url'])
                lede += utils.add_video(video['streams'][0]['url'], video['streams'][0]['type'], poster, caption)
            else:
                lede += add_video(story_json['lede']['id'])
        else:
            logger.warning('unhandled lede type {} in {}'.format(story_json['lede']['type'], item['url']))
    elif story_json.get('ledeMediaKind'):
        item['_image'] = story_json['ledeImageUrl']
        captions = []
        if story_json.get('ledeCaption'):
            captions.append(story_json['ledeCaption'])
        if story_json.get('ledeDescription'):
            captions.append(story_json['ledeDescription'])
        if story_json.get('ledeCredit'):
            captions.append(story_json['ledeCredit'])
        caption = re.sub(r'<p>|</p>', '', ' | '.join(captions))
        if story_json['ledeMediaKind'] == 'image':
            lede += utils.add_image(resize_image(story_json['ledeImageUrl']), caption)
        elif story_json['ledeMediaKind'] == 'video':
            lede += add_video(story_json['ledeAttachment']['bmmrId'])
    elif story_json.get('imageAttachments'):
        img_id = [*story_json['imageAttachments']][0]
        image = story_json['imageAttachments'][img_id]
        if image.get('baseUrl'):
            item['_image'] = image['baseUrl']
        elif image.get('url'):
            item['_image'] = image['url']
        if body and not body.find('figure', attrs={"data-id": img_id}):
            captions = []
            if image.get('caption'):
                captions.append(image['caption'])
            elif image.get('title'):
                captions.append(image['title'])
            if image.get('credit'):
                captions.append(image['credit'])
            caption = re.sub(r'<p>|</p>', '', ' | '.join(captions))
            lede += utils.add_image(resize_image(item['_image']), caption)
    if lede:
        item['content_html'] += lede

    if 'embed' in args:
        item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(item['url']).netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        if story_json.get('abstract'):
            item['content_html'] += '<ul style="font-size:0.9em;">'
            for it in story_json['abstract']:
                item['content_html'] += '<li>{}</li>'.format(it)
            item['content_html'] += '</ul>'
        item['content_html'] += '<p><a href="{}/content?read&url={}" target="_blank">Read</a></p></div></div><div>&nbsp;</div>'.format(config.server, quote_plus(item['url']))
        return item

    if body:
        for el in body.find_all(attrs={"data-ad-placeholder": "Advertisement"}):
            el.decompose()

        for el in body.find_all(class_=re.compile(r'-footnotes|for-you|-newsletter|page-ad|-recirc')):
            el.decompose()

        for el in body.find_all('a', href=re.compile(r'^\/')):
            el['href'] = 'https://www.bloomberg.com' + el['href']

        for el in body.find_all(['meta', 'script']):
            el.decompose()

        if save_debug:
            utils.write_file(body.prettify(), './debug/debug.html')

        for el in body.find_all('figure'):
            new_html = ''
            if el.get('data-image-type') == 'chart':
                if story_json['imageAttachments'].get(el['data-id']):
                    image = story_json['imageAttachments'][el['data-id']]
                    img_src = resize_image(image['baseUrl'])
                    if image.get('themes'):
                        theme = next((it for it in image['themes'] if it['id'] == 'white_background'), None)
                        if theme:
                            img_src = resize_image(theme['url'])
                    captions = []
                    it = el.find('div', class_='caption')
                    if it and it.get_text().strip():
                        captions.append(it.get_text().strip())
                    it = el.find('div', class_='credit')
                    if it and it.get_text().strip():
                        captions.append(it.get_text().strip())
                    new_html = utils.add_image(img_src, ' | '.join(captions))
                else:
                    chart = next((it for it in story_json['charts'] if it['id'] == el['data-id']), None)
                    if chart:
                        if chart.get('responsiveImages') and chart['responsiveImages'].get('mobile'):
                            img_src = resize_image(chart['responsiveImages']['mobile']['url'])
                            captions = []
                            if chart.get('subtitle'):
                                captions.append(chart['subtitle'])
                            if chart.get('source'):
                                captions.append(chart['source'])
                            if chart.get('footnote'):
                                captions.append(chart['footnote'])
                            new_html = utils.add_image(img_src, ' | '.join(captions))
                if not new_html:
                    logger.warning('unhandled chart {} in {}'.format(el['data-id'], item['url']))

            elif el.get('data-image-type') == 'audio':
                poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(el.img['src']))
                it = el.find('div', class_='caption')
                if it and it.get_text().strip():
                    caption = it.get_text().strip()
                else:
                    caption = 'Listen'
                it = el.find('div', class_='credit')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
                else:
                    credit = 'Bloomberg Radio'
                new_html = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div><h4 style="margin-top:0; margin-bottom:0.5em;">{}</h4><small>{}</small></div><div style="clear:left;">&nbsp;</div></div>'.format(
                    el.source['src'], poster, caption, credit)

            elif el.get('data-image-type') == 'video':
                video = story_json['videoAttachments'][el['data-id']]
                new_html = add_video(video['bmmrId'])

            elif el.get('data-image-type') == 'photo' or el.get('data-type') == 'image':
                image = story_json['imageAttachments'][el['data-id']]
                img_src = resize_image(image['baseUrl'])
                if image.get('themes'):
                    theme = next((it for it in image['themes'] if it['id'] == 'white_background'), None)
                    if theme:
                        img_src = resize_image(theme['url'])
                captions = []
                it = el.find('div', class_='caption')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                it = el.find('div', class_='credit')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                new_html = utils.add_image(img_src, ' | '.join(captions))

            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in body.find_all('div', class_='thirdparty-embed'):
            new_html = ''
            if el.blockquote and ('twitter-tweet' in el.blockquote['class']):
                m = re.findall(r'https:\/\/twitter\.com\/[^\/]+\/statuse?s?\/\d+', str(el.blockquote))
                new_html += utils.add_embed(m[-1])

            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in body.find_all(class_='thirdparty-embed'):
            new_html = ''
            it = el.find(class_='instagram-media')
            if it:
                new_html = utils.add_embed(it['data-instgrm-permalink'])
            elif el.iframe:
                new_html = utils.add_embed(el.iframe['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled embed in ' + item['url'])

        for el in body.find_all(class_='paywall'):
            el.attrs = {}

        # remove empty paragraphs
        item['content_html'] += re.sub(r'<p\b[^>]*>(&nbsp;|\s)<\/p>', '', str(body))

    elif isinstance(story_json['body'], dict) and story_json['body'].get('content'):
        for content in story_json['body']['content']:
            item['content_html'] += format_content(content, story_json.get('imageAttachments'))
        if story_json.get('footer') and story_json['footer'].get('content'):
            item['content_html'] += '<hr/>'
            for content in story_json['footer']['content']:
                item['content_html'] += format_content(content, story_json.get('imageAttachments'))

    if story_json.get('footnotes') and story_json['footnotes'].get('content'):
        item['content_html'] += '<hr/>'
        for content in story_json['footnotes']['content']:
            item['content_html'] += format_content(content, story_json.get('imageAttachments'))

    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.rss'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    urls = []
    split_url = urlsplit(args['url'])
    paths = split_url.path[1:].split('/')

    if 'newsletters' in paths:
        if paths[-1] == 'latest':
            # https://www.bloomberg.com/newsletters/five-things/latest
            urls.append(utils.get_redirect_url(args['url']))
        else:
            # https://www.bloomberg.com/account/newsletters
            bb_json = utils.get_url_json('https://login.bloomberg.com/api/newsletters/list?email=&hash=')
            if bb_json:
                for key in ['daily', 'weekly']:
                    for val in bb_json[key]:
                        if val.get('sampleUrl'):
                            urls.append(val['sampleUrl'])
                        elif val.get('variants'):
                            for v in val['variants']:
                                if v.get('sampleUrl'):
                                    urls.append(v['sampleUrl'])
    else:
        page_html = get_bb_url(url)
        if save_debug:
            utils.write_file(page_html, './debug/debug.html')
        if page_html:
            soup = BeautifulSoup(page_html, 'html.parser')
            for el in soup.find_all(attrs={"data-component": "headline"}):
                it = el.find('a')
                if it:
                    print(it['href'])

            el = soup.find('script', id='__NEXT_DATA__')
            if el:
                next_data = json.loads(el.string)
                if save_debug:
                    utils.write_file(next_data, './debug/next_data.json')
                modules = []
                module_types = []
                module_variations = []
                for zone in next_data['props']['pageProps']['initialState']['curation']['zones']:
                    if zone.get('columns'):
                        for column in zone['columns']:
                            if column.get('modules'):
                                for module in column['modules']:
                                    if module['__typename'] == 'CurationModule':
                                        modules.append(module['id'])
                                        if module.get('type'):
                                            module_types.append(module['type'])
                                        if module.get('variation'):
                                            module_variations.append(module['variation'])
                api_url = 'https://www.bloomberg.com/lineup-next/api/page/{}/module/{}?moduleVariations={}&moduleTypes={}&locale=en&publishedState=PUBLISHED'.format(paths[0], ','.join(modules), ','.join(module_variations), ','.join(module_types))
                print(api_url)
                api_json = get_bb_url(api_url, True)
                if api_json:
                    if save_debug:
                        utils.write_file(api_json, './debug/feed.json')
                    stories = {}
                    for key, module in api_json['modules'].items():
                        for it in module['items']:
                            if it['__modelType'] == 'Story' and not stories.get(it['id']):
                                stories[it['id']] = it
                for key, val in stories.items():
                    if val['type'] == 'video':
                        print('video ' + val['id'])
                    else:
                        print(val['url'])

        if len(paths) > 1:
            logger.warning('unsupported feed ' + args['url'])
            return None

        if paths[0] in ['markets', 'technology', 'politics', 'wealth', 'pursuits']:
            page = paths[0] + '-vp'
        elif paths[0] == 'businessweek':
            page = 'businessweek-v2'
        else:
            page = paths[0]
        api_url = 'https://www.bloomberg.com/lineup/api/lazy_load_paginated_module?id=pagination_story_list&page={}&offset=0&zone=righty'.format(page)
        bb_json = get_bb_url(api_url, True)
        if save_debug:
            utils.write_file(bb_json, './debug/feed.json')
        if not bb_json:
            return None
        soup = BeautifulSoup(bb_json['html'], 'html.parser')
        for el in soup.find_all('a', class_='story-list-story__info__headline-link'):
            urls.append('https://www.bloomberg.com' + el['href'])

    n = 0
    items = []
    for url in urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


# https://www.bloomberg.com/lineup-next/api/storiesById/RZRGMAT0G1KW01