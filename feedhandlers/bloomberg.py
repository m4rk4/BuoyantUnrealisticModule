import feedparser, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)

def resize_image(img_src):
    return re.sub(r'[\d-]+x[\d-]+.(jpg|png)', '1024x-1.\\1', img_src)


def get_bb_url(url, get_json=False):
    #print(url)
    headers = {
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "cache-control": "max-age=0",
        "sec-ch-ua": "\"Chromium\";v=\"106\", \"Microsoft Edge\";v=\"106\", \"Not;A=Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "sec-gpc": "1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.47"
    }
    if get_json:
        headers['accept'] = 'application/json'
        content = utils.get_url_json(url, headers=headers, allow_redirects=False)
    else:
        headers['accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9'
        content = utils.get_url_html(url, headers=headers, allow_redirects=False)
    if not content:
        # Try through browser
        content = utils.get_browser_request(url, get_json)
    return content


def add_video(video_id):
    #api_url = 'https://www.bloomberg.com/multimedia/api/embed?id=' + video_id
    api_url = 'https://www.bloomberg.com/media-manifest/embed?id=' + video_id
    video_json = get_bb_url(api_url, True)
    if video_json:
        if video_json.get('description'):
            caption = video_json['description']
        elif video_json.get('title'):
            caption = video_json['title']
        poster = resize_image('https:' + video_json['thumbnail']['baseUrl'])
        return utils.add_video(video_json['downloadURLs']['600'], 'video/mp4', poster, caption)
    else:
        logger.warning('error getting video json ' + api_url)
        return ''


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


def get_newsletter_content(url, args, site_json, save_debug):
    bb_html = get_bb_url(url)
    if save_debug:
        utils.write_file(bb_html, './debug/debug.html')
    if not bb_html:
        return None

    soup = BeautifulSoup(bb_html, 'html.parser')
    el = soup.find('script', attrs={"type": "application/json", "data-component-props": "OverlayAd"})
    if not el:
        logger.warning('unable to find newsletter props in ' + url)
        return None
    article_json = json.loads(el.string)
    return get_item(article_json, args, site_json, save_debug)


def get_content(url, args, site_json, save_debug):
    if '/videos/' in url:
        return get_video_content(url, args, site_json, save_debug)
    elif '/newsletters/' in url:
        return get_newsletter_content(url, args, site_json, save_debug)

    api_url = ''
    split_url = urlsplit(url)
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

    bb_json = get_bb_url(api_url, True)
    if not bb_json:
        return None
    if save_debug:
        utils.write_file(bb_json, './debug/content.json')

    soup = BeautifulSoup(bb_json['html'], 'html.parser')
    el = soup.find('script', attrs={"data-component-props": re.compile(r'ArticleBody|FeatureBody')})
    if not el:
        logger.warning('unable to find ArticleBody in ' + url)
        return None
    article_json = json.loads(el.string)
    return get_item(article_json, args, site_json, save_debug)


def get_item(article_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['story']['id']
    item['url'] = article_json['story']['canonical']
    item['title'] = article_json['story']['textHeadline']

    dt = datetime.fromisoformat(article_json['story']['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['story']['updatedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    authors = []
    for author in article_json['story']['authors']:
        authors.append(author['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json['story'].get('mostRelevantTags'):
        item['tags'] = article_json['story']['mostRelevantTags'].copy()

    item['summary'] = article_json['story']['teaserBody']

    item['content_html'] = ''

    # el = soup.find('ul', class_='abstract-v2')
    # if el:
    #  item['content_html'] += str(el)

    if article_json['story'].get('dek'):
        item['content_html'] += article_json['story']['dek']

    if article_json['story'].get('abstract'):
        item['content_html'] += '<ul>'
        for it in article_json['story']['abstract']:
            item['content_html'] += '<li>{}</li>'.format(it)
        item['content_html'] += '</ul>'

    body = BeautifulSoup(article_json['story']['body'], 'html.parser')

    lede = ''
    if article_json['story'].get('ledeMediaKind'):
        item['_image'] = article_json['story']['ledeImageUrl']
        captions = []
        if article_json['story'].get('ledeCaption'):
            captions.append(article_json['story']['ledeCaption'])
        if article_json['story'].get('ledeDescription'):
            captions.append(article_json['story']['ledeDescription'])
        if article_json['story'].get('ledeCredit'):
            captions.append(article_json['story']['ledeCredit'])
        caption = re.sub(r'<p>|<\/p>', '', ' | '.join(captions))
        if article_json['story']['ledeMediaKind'] == 'image':
            lede += utils.add_image(resize_image(article_json['story']['ledeImageUrl']), caption)
        elif article_json['story']['ledeMediaKind'] == 'video':
            lede += add_video(article_json['story']['ledeAttachment']['bmmrId'])
    elif article_json['story'].get('imageAttachments'):
        img_id = [*article_json['story']['imageAttachments']][0]
        image = article_json['story']['imageAttachments'][img_id]
        item['_image'] = image['baseUrl']
        if not body.find('figure', attrs={"data-id": img_id}):
            lede += utils.add_image(resize_image(image['baseUrl']), image['caption'])
    if lede:
        item['content_html'] += lede

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
            if article_json['story']['imageAttachments'].get(el['data-id']):
                image = article_json['story']['imageAttachments'][el['data-id']]
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
                chart = next((it for it in article_json['story']['charts'] if it['id'] == el['data-id']), None)
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
            video = article_json['story']['videoAttachments'][el['data-id']]
            new_html = add_video(video['bmmrId'])

        elif el.get('data-image-type') == 'photo' or el.get('data-type') == 'image':
            image = article_json['story']['imageAttachments'][el['data-id']]
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
            m = re.findall('https:\/\/twitter\.com\/[^\/]+\/statuse?s?\/\d+', str(el.blockquote))
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
    return item


def get_feed(url, args, site_json, save_debug=False):
    urls = []
    split_url = urlsplit(args['url'])
    paths = split_url.path[1:].split('/')

    if args['url'].endswith('.rss'):
        rss_feed = utils.get_url_html(args['url'])
        if rss_feed:
            d = feedparser.parse(rss_feed)
            for entry in d.entries:
                urls.append(entry.link)
    elif 'newsletters' in paths:
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
