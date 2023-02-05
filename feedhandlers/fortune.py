import math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def format_value(value, decimals=2):
    if not value:
        return '—'
    try:
        if '.' in value:
            if decimals == 2:
                return '{:,.2f}'.format(float(value))
            elif decimals == 1:
                return '{:,.1f}'.format(float(value))
            elif decimals == 0:
                return '{:,.0f}'.format(float(value))
        else:
            return '{:,}'.format(int(value))
    except:
        return value


def format_data(data):
    if not data['value']:
        return '—'
    if data['fieldMeta']['type'] == 'Money':
        return '$' + format_value(data['value'])
    elif data['fieldMeta']['type'] == 'Percent':
        return format_value(data['value']) + '%'
    elif data['fieldMeta']['type'] == 'Link':
        return '<a href="{0}">{0}</a>'.format(data['value'])


def get_tokens():
    token = ''
    api_key = ''
    main_js = utils.get_url_html('https://fortune.com/static/js/main.chunk.js')
    m = re.search(r'BASIC_AUTH_TOKEN\|\|"([^"]+)"', main_js)
    if m:
        token = m.group(1)

    m = re.search(r'c="([^"]+)",s="https://video-api\.fortune\.com/v1/public/video/"', main_js)
    if m:
        api_key = m.group(1)
    return token, api_key


def get_api_content(type, value, retry=True):
    api_json = None
    sites_json = utils.read_json_file('./sites.json')

    if type == 'page':
        split_url = urlsplit(value)
        api_url = 'https://fortune.com/wp-json/irving/v1/components?context=page&path={}&token={}'.format(quote_plus(split_url.path), sites_json['fortune']['token'])
        api_json = utils.get_url_json(api_url)

    elif type == 'video':
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9,de;q=0.8",
            "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"98\", \"Microsoft Edge\";v=\"98\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "x-api-key": sites_json['fortune']['api_key']
        }
        api_json = utils.get_url_json('https://video-api.fortune.com/v1/public/video/{}'.format(value), headers=headers)

    elif type == 'historical':
        api_url = 'https://fortune.com/wp-json/irving/v1/data/company-child-historical-results?comp_id={}&list_id={}&token={}'.format(value[0], value[1], sites_json['fortune']['token'])
        api_json = utils.get_url_json(api_url)

    if not api_json and retry:
        # Check for new tokens
        token, api_key = get_tokens()
        if token != sites_json['fortune']['token'] or api_key != sites_json['fortune']['api_key']:
            logger.debug('updating fortune.com tokens')
            sites_json['fortune']['token'] = token
            sites_json['fortune']['api_key'] = api_key
            utils.write_file(sites_json, './sites.json')
            api_json = get_api_content(type, value, False)
    return api_json


def add_video(video_id):
    video_json = get_api_content('video', video_id)
    if not video_json:
        return ''

    if False:
        utils.write_file(video_json, './debug/video.json')

    split_url = urlsplit(video_json['originalImage'])
    video_src = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, video_json['hlsFormat']['key'])

    caption = video_json['name']
    if video_json.get('shortDescription'):
        caption += ' | ' + video_json['shortDescription']
    elif video_json.get('longDescription'):
        caption += ' | ' + video_json['longDescription']

    return utils.add_video(video_src, 'application/x-mpegURL', video_json['originalImage'], caption)


def resize_image(image, width=1000):
    height = math.ceil(width * image['aspectRatio'])
    return utils.clean_url(image['src']) + '?resize={},{}'.format(width, height)


def add_image(image, width=1000):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    return utils.add_image(resize_image(image, width), ' | '.join(captions))


def render_content(content):
    content_html = ''
    for child in content['children']:
        #print(child['name'])

        if re.search(r'\b(advertising|byline|pagination|sidebar|social)\b', child['name']) or (child['name'] == 'dianomi' and child['config']['type'] == 'sidebar'):
            continue

        if 'hero' in child['name']:
            if child['config'].get('dek'):
                content_html += '<p>{}</p>'.format(child['config']['dek'])
            if child['config'].get('description'):
                content_html += render_content(child)
                content_html += '<p>{}</p>'.format(child['config']['description'])
                continue
        elif child['name'] == 'grid':
            if child['config'].get('heading'):
                if re.search(r'^(Related|More)', child['config']['heading']):
                    continue
                content_html += '<h3>{}</h3>'.format(child['config']['heading'])

        if re.search(r'\b(body|content(?!-item)|description|grid|header|hero|media|modules|wrapper)\b', child['name']):
            #if re.search(r'\b(body|content|description|grid|header|hero|media|modules|wrapper)\b', child['name']):
            content_html += render_content(child)
            continue

        if child['name'] == 'html':
            content_html += child['config']['content']

        elif child['name'] == 'image' or child['name'] == 'background-image':
            content_html += add_image(child['config'])

        elif child['name'] == 'vod-video':
            if '-' in str(child['config']['videoId']):
                content_html += add_video(child['config']['videoId'])
            else:
                logger.warning('invalid videoId {}'.format(child['config']['videoId']))

        elif child['name'] == 'core-embed':
            if child['config']['provider'] == 'twitter':
                m = re.findall('https:\/\/twitter\.com\/[^\/]+\/statuse?s?\/\d+', child['config']['content'])
                content_html += utils.add_embed(m[-1])
            elif child['config']['provider'] == 'youtube':
                m = re.search('src="([^"]+)"', child['config']['content'])
                content_html += utils.add_embed(m.group(1))
            elif child['config']['provider'] == 'instagram':
                m = re.search(r'data-instgrm-permalink="([^"\?]+)', child['config']['content'])
                content_html += utils.add_embed(m.group(1))
            elif child['config']['provider'] == 'tiktok':
                m = re.search(r'cite="([^"\?]+)', child['config']['content'])
                content_html += utils.add_embed(m.group(1))
            elif child['config']['provider'] == 'datawrapper':
                m = re.search(r'src="([^"\?]+)', child['config']['content'])
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled core-embed ' + child['config']['provider'])

        elif child['name'] == 'interactive':
            content_html += '<h3>{0}</h3><blockquote>Interactive content: <a href="{1}">{1}</a></blockquote><br/>'.format(child['config']['heading'], child['config']['interactiveUrl'])

        elif child['name'] == 'content-item':
            dt = datetime.fromisoformat(child['config']['publishDateIso8601']).astimezone(timezone.utc)
            date = utils.format_display_date(dt)
            image = next((it for it in child['children'] if it['name'] == 'image'), None)
            if image['config'].get('src'):
                content_html += '<div style="margin-bottom:1em;"><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;"><h4 style="margin-top:0; margin-bottom:0;"><a href="{}">{}</a></h4><small>{}</small><br/>{}</div><div style="clear:left;"></div></div>'.format(child['config']['permalink'], resize_image(image['config'], 128), child['config']['permalink'], child['config']['title'], date, child['config']['excerpt'])
            else:
                content_html += '<div style="margin-bottom:1em;"><h4 style="margin-top:0; margin-bottom:0;"><a href="{}">{}</a></h4><small>{}</small><br/>{}</div>'.format(child['config']['permalink'], child['config']['title'], date, child['config']['excerpt'])

        elif child['name'] == 'franchise-highlighted-stats':
            content_html += '<ul>'
            for data in child['config']['stats']:
                content_html += '<li>{}: {}</li>'.format(data['fieldMeta']['title'], format_data(data))
            content_html += '</ul>'

        elif child['name'] == 'franchise-data-table':
            content_html += '<h3>{}</h3><ul>'.format(child['config']['title'])
            for data in child['config']['data']:
                content_html += '<li>{}: {}</li>'.format(data['fieldMeta']['title'], format_data(data))
            content_html += '</ul>'

        elif child['name'] == 'franchise-list-teaser':
            content_html += '<h2>{}</h2>'.format(child['config']['years']['config']['year'])
            content_html += render_content(child)

        elif child['name'] == 'franchise-list-teaser-item':
            title = '<a href="{}">{}</a>'.format(child['config']['permalink'], child['config']['title'])
            if child['config'].get('rank'):
                title = '{}. {}'.format(child['config']['rank'], title)
            image = next((it for it in child['children'] if it['name'] == 'image'), None)
            if image:
                content_html += '<div style="margin-bottom:1em;"><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;"><h4 style="margin-top:0; margin-bottom:0;">{}</h4></div><div style="clear:left;"></div></div>'.format(child['config']['permalink'], image['config']['lqipSrc'], title)
            else:
                content_html += '<h4>{}</h4>'.format(title)

        elif child['name'] == 'company-title':
            if child['config'].get('rank'):
                content_html += '<h3>{} Rank: {}</h3>'.format(child['config']['franchiseTitle'], child['config']['rank'])

        elif child['name'] == 'company-latest-news':
            if child.get('children'):
                content_html += '<h3>Latest news:</h3>'
                content_html += render_content(child)

        elif child['name'] == 'company-latest-videos':
            if child.get('children'):
                content_html += '<h3>Latest videos:</h3>'
                content_html += render_content(child)

        elif child['name'] == 'company-information':
            content_html += '<div  class="company_info"><h3>{} <span style="font-size:0.8em; font-weight:normal;">(As of {})</span></h3><figure><table>'.format(child['config']['title'], child['config']['updated'])
            content_html += '<tr><td style="padding-right:1em;">Country</td><td>{}</td></tr>'.format(child['config']['country'])
            content_html += '<tr><td style="padding-right:1em;">Headquarters</td><td>{}</td></tr>'.format(child['config']['headquarters'])
            content_html += '<tr><td style="padding-right:1em;">Industry</td><td>{}</td></tr>'.format(child['config']['industry'])
            content_html += '<tr><td style="padding-right:1em;">CEO</td><td>{}</td></tr>'.format(child['config']['ceo'])
            content_html += '<tr><td style="padding-right:1em;">Website</td><td><a href="{0}">{0}</a></td></tr>'.format(child['config']['website'])
            content_html += '<tr><td style="padding-right:1em;">Company Type</td><td>{}</td></tr>'.format(child['config']['companyType'])

            value = format_value(child['config']['ticker'])
            content_html += '<tr><td style="padding-right:1em;">Ticker</td><td>{}</td></tr>'.format(value)

            value = format_value(child['config']['revenues'])
            content_html += '<tr><td style="padding-right:1em;">Revenues ($M)</td><td>${}</td></tr>'.format(value)

            value = format_value(child['config']['profits'])
            content_html += '<tr><td style="padding-right:1em;">Profits ($M)</td><td>${}</td></tr>'.format(value)

            value = format_value(child['config']['marketValue'])
            content_html += '<tr><td style="padding-right:1em;">Market Value ($M)</td><td>${}</td></tr>'.format(value)

            value = format_value(child['config']['employees'])
            content_html += '<tr><td style="padding-right:1em;">Employees</td><td>{}</td></tr>'.format(value)

            content_html += '</table><figcaption><small>{}</small></figcaption></figure></div>'.format(child['config']['footnote'])

        elif child['name'] == 'company-data-table':
            content_html += '<h3>{}'.format(child['config']['title'])
            if child['config'].get('updated'):
                content_html += ' <span style="font-size:0.8em; font-weight:normal;">(As of {})</span>'.format(child['config']['updated'])
            content_html += '</h3><figure><table>'
            if child['config'].get('showChange'):
                content_html += '<tr><th></th><th style="padding-right:1em;">{}</th><th>{}</th></tr>'.format(child['config']['valueHeader'], child['config']['changeHeader'])
                for i, data in enumerate(child['config']['data']):
                    content_html += '<tr><td style="padding-right:1em;">{}</td><td style="padding-right:1em;">{}</td><td>{}</td></tr>'.format(data['fieldMeta']['title'], format_data(data), format_data(child['config']['change'][i]))
            else:
                if child['config'].get('valueHeader'):
                    content_html += '<tr><th></th><th>{}</th></tr>'.format(child['config']['valueHeader'])
                for i, data in enumerate(child['config']['data']):
                    content_html += '<tr><td style="padding-right:1em;">{}</td><td>{}</td></tr>'.format(data['fieldMeta']['title'], format_data(data))
            if child['config'].get('footnote'):
                content_html += '</table><figcaption><small>{}</small></figcaption></figure><br/>'.format(child['config']['footnote'])
            else:
                content_html += '</table></figure><br/>'

        elif child['name'] == 'company-historical':
            content_html += '<h3>Historical Data</h3>'
            data = get_api_content('historical', [child['config']['companyId'], child['config']['franchiseId']])
            if data:
                content_html += '<figure><table><tr><th>Year</th><th>Revenues ($M)</th><th>Profits ($M)</th><th>Assets ($M)</th><th>Total Stockholder Equity ($M)</th></tr>'
                for i in range(len(data['year'])):
                    content_html += '<tr><td style="padding-right:1em;">{}</td><td style="padding-right:1em;">${} ({}%)</td><td style="padding-right:1em;">${} ({}%)</td><td style="padding-right:1em;">${}</td><td>${}</td></tr>'.format(data['year'][i], format_value(data['revenue'][i], 0), format_value(data['revchange'][i], 1), format_value(data['profit'][i], 0), format_value(data['prftchange'][i], 1), format_value(data['assets'][i], 0), format_value(data['equity'][i], 0))
                content_html += '</table></figure><br/>'
            else:
                content_html += '<blockquote>Unable to get historical data</blockquote><br/>'

        else:
            logger.warning('unhandled content ' + child['name'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    api_json = get_api_content('page', url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_json = next((page['config']['metadata'] for page in api_json['page'] if page['name'] == 'parsely'), None)

    item = {}
    item['id'] = article_json['identifier']
    item['url'] = article_json['url']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    if article_json.get('author'):
        authors = []
        for author in article_json['author']:
            authors.append(author['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('keywords'):
        item['tags'] = article_json['keywords'].copy()

    if article_json.get('image'):
        item['_image'] = article_json['image']

    if article_json.get('description'):
        item['summary'] = article_json['description']

    body_page = next((page for page in api_json['page'] if page['name'] == 'body'), None)
    content_html = render_content(body_page)

    soup = BeautifulSoup(content_html, 'html.parser')
    el = soup.find(class_='paywall')
    if el:
        el.unwrap()

    for el in soup.find_all(class_='wp-block-image'):
        img_src = ''
        if el.img:
            if el.img.get('data-src'):
                img_src = el.img['data-src']
            elif el.img.get('src'):
                img_src = el.img['data-src']
        caption = ''
        if el.figcaption:
            caption = el.figcaption.get_text()
        link = ''
        if el.a:
            link = el.a['href']
        new_html = utils.add_image(img_src, caption, link=link)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all(class_=re.compile(r'wp-block-(pull)?quote')):
        if el.blockquote:
            el_quote = el.blockquote
        else:
            el_quote = el
        cite = ''
        if el.cite:
            cite = el.cite.get_text()
        new_html = utils.add_pullquote(str(el_quote.p), cite)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all(class_=re.compile(r'favorites_widget|paywall-selector|plea-block')):
        el.decompose()

    el = soup.find_all(class_='company_info')
    if len(el) > 1:
        el[-1].decompose()

    item['content_html'] = str(soup)
    return item

def get_feed(url, args, site_json, save_debug=False):
    # https://fortune.com/feed/?tag=datasheet
    if '/feed' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    api_json = get_api_content('page', args['url'])
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    article_ids = []
    article_links = []
    def iter_children(section):
        nonlocal article_ids
        nonlocal article_links
        for child in section['children']:
            if 'sidebar' in child['name']:
                continue
            if child.get('config'):
                if child['config'].get('id') and child['config']['permalink']:
                    if not child['config']['id'] in article_ids:
                        article_ids.append(child['config']['id'])
                        article_links.append(child['config']['permalink'])
            if child.get('children'):
                iter_children(child)

    body_json = next((page for page in api_json['page'] if page['name'] == 'body'), None)
    iter_children(body_json)

    n = 0
    items = []
    for url in article_links:
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

#https://fortune.com/education/page-data/business/mba/rankings/best-mba-programs/page-data.json