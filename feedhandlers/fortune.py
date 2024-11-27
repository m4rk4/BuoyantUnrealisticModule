import json, math, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
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

        if re.search(r'\b(advertising|byline|favorites-list|pagination|sidebar|social)\b', child['name']) or (child['name'] == 'dianomi' and child['config']['type'] == 'sidebar'):
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
                m = re.findall(r'https:\/\/twitter\.com\/[^\/]+\/statuse?s?\/\d+', child['config']['content'])
                content_html += utils.add_embed(m[-1])
            elif child['config']['provider'] == 'youtube':
                m = re.search(r'src="([^"]+)"', child['config']['content'])
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

        elif child['name'] == 'dianomi' and child.get('config') and child['config'].get('type') and (child['config']['type'] == 'footer' or child['config']['type'] == 'sidebar'):
            continue

        else:
            logger.warning('unhandled content ' + child['name'])
    return content_html


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
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


def get_content(url, args, site_json, save_debug=False):
    if '/videos/' in url:
        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path.split('/')))
        api_url = 'https://fortune.com/v1/public/video/' + paths[-1]
        headers = {
            "x-api-key": site_json['api_key']
        }
        video_json = utils.get_url_json(api_url, headers=headers)
        if not video_json:
            return None
        if save_debug:
            utils.write_file(video_json, './debug/debug.json')
        item = {}
        item['id'] = video_json['videoId']
        item['url'] = url
        item['title'] = video_json['name']

        tz_loc = pytz.timezone('US/Eastern')
        dt_loc = datetime.fromtimestamp(video_json['videoPublishDate'] / 1000)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        item['author'] = {
            "name": "Fortune On-Demand"
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['tags'] = []
        if video_json.get('section'):
            item['tags'].append(video_json['section']['name'])
        if video_json.get('categories'):
            item['tags'] += [x['name'] for x in video_json['categories']]
        if video_json.get('tags'):
            item['tags'] += [x['label'] for x in video_json['tags']]
        if len(item['tags']) == 0:
            del item['tags']

        if video_json.get('resizedOriginalImages'):
            item['image'] = video_json['resizedOriginalImages'][0]
        else:
            item['image'] = video_json['originalImage']

        if video_json.get('longDescription'):
            item['summary'] = video_json['longDescription']
        elif video_json.get('shortDescription'):
            item['summary'] = video_json['shortDescription']
    
        api_url = 'https://fortune.com/v1/public/video-url?videoId={}&mediaFormatType=hlsFormat'.format(item['id'])
        video_url = utils.get_url_html(api_url, headers=headers)
        if video_url:
            item['content_html'] = utils.add_video(video_url, 'application/x-mpegURL', item['image'], item['title'])
        else:
            item['content_html'] = utils.add_image(item['image'], '<b>Video unavailable.</b> <a href="{}" target="_blank">{}</a>'.format(item['url'], item['title']))

        if 'embed' not in args:
            if 'summary' in item:
                item['content_html'] += '<p>' + item['summary'] + '</p>'
            if video_json.get('transcript'):
                item['content_html'] += '<h3>Transcript</h3><p>' + video_json['transcript'] + '</p>'

    else:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/next.json')

        head_data = next_data['pageProps']['headData']
        if head_data['pageType'] == 'article' or head_data['pageType'] == 'evergreen':
            article_json = next_data['pageProps']['article']
        elif head_data['pageType'] == 'franchise-list':
            article_json = next_data['pageProps']['franchise']
        elif head_data['pageType'] == 'edu-rankings-list':
            article_json = next_data['pageProps']['rankingList']
        else:
            logger.warning('unhandled page type {} for {}'.format(head_data['pageType'], url))
            return None
        if save_debug:
            utils.write_file(article_json, './debug/debug.json')

        if head_data.get('jsonLdSchema'):
            ld_json = json.loads(head_data['jsonLdSchema'])
        else:
            ld_json = None

        item = {}
        if article_json.get('postId'):
            item['id'] = article_json['postId']
        elif article_json.get('databaseId'):
            item['id'] = article_json['databaseId']
        else:
            logger.warning('unknown article id for ' + url)

        if article_json.get('link'):
            item['url'] = article_json['link']
        elif head_data.get('canonicalUrl'):
            item['url'] = head_data['canonicalUrl']
        else:
            item['url'] = url
        split_url = urlsplit(item['url'])

        item['title'] = article_json['title']

        if article_json.get('dateGmt'):
            if article_json['dateGmt'].isnumeric():
                dt = datetime.fromtimestamp(int(article_json['dateGmt'])).replace(tzinfo=timezone.utc)
            else:
                dt = datetime.fromisoformat(article_json['dateGmt']).replace(tzinfo=timezone.utc)
        elif head_data.get('dateGmt'):
            dt = datetime.fromisoformat(head_data['dateGmt']).replace(tzinfo=timezone.utc)
        elif ld_json and ld_json.get('datePublished'):
            dt = datetime.fromisoformat(ld_json['datePublished']).astimezone(timezone.utc)
        else:
            dt = None
        if dt:
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
        if article_json.get('modifiedGmt'):
            if article_json['modifiedGmt'].isnumeric():
                dt = datetime.fromtimestamp(int(article_json['modifiedGmt'])).replace(tzinfo=timezone.utc)
            else:
                dt = datetime.fromisoformat(article_json['modifiedGmt']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

        if article_json.get('authorNames'):
            item['authors'] = [{"name": x} for x in article_json['authorNames']]
            if len(item['authors']) > 0:
                item['author'] = {
                    "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['authorNames']))
                }
            else:
                del item['authors']
        else:
            if head_data.get('siteName'):
                item['author'] = {
                    "name": head_data['siteName']
                }
            else:
                item['author'] = {
                    "name": split_url.netloc
                }
            item['authors'] = []
            item['authors'].append(item['author'])

        item['tags'] = []
        if article_json.get('sectionNames'):
            item['tags'] += article_json['sectionNames'].copy()
        if article_json.get('tagNames'):
            item['tags'] += article_json['tagNames'].copy()
        if len(item['tags']) == 0:
            del item['tags']

        if article_json.get('featuredImage'):
            item['image'] = article_json['featuredImage']
        elif article_json.get('image'):
            if isinstance(article_json['image'], str):
                item['image'] = article_json['image']
            elif isinstance(article_json['image'], dict):
                item['image'] = article_json['image']['mediaItemUrl']

        if article_json.get('description'):
            item['summary'] = article_json['description']

        if 'embed' in args:
            item['content_html'] = utils.format_embed_preview(item)
            return item

        item['content_html'] = ''
        if article_json.get('dek'):
            item['content_html'] += '<p><em>' + article_json['dek'] + '</em></p>'

        lede = ''
        if article_json.get('featuredMediaType') and article_json['featuredMediaType'] == 'stn_video_media':
            lede += utils.add_embed('https://embed.sendtonews.com/player2/embedcode.php?SC={}&autoplay=on'.format(article_json['videoId']))
            if lede.startswith('<blockquote'):
                lede = ''
        if not lede:
            if article_json.get('image'):
                captions = []
                if isinstance(article_json['image'], str):
                    if article_json.get('imageCaption'):
                        captions.append(article_json['imageCaption'])
                    if article_json.get('imageCredit'):
                        captions.append(article_json['imageCredit'])
                    img_src = article_json['image']
                else:
                    if article_json['image'].get('caption'):
                        captions.append(article_json['image']['caption'])
                    if article_json['image'].get('credit'):
                        captions.append(article_json['image']['credit'])
                    img_src = article_json['image']['mediaItemUrl']
                lede += utils.add_image(img_src, ' | '.join(captions))
            elif article_json.get('featuredImage'):
                lede += utils.add_image(article_json['featuredImage'])
        item['content_html'] += lede

        if article_json.get('content'):
            content = BeautifulSoup(article_json['content'], 'html.parser')
            for el in content.find_all(class_='paywall-selector'):
                el.decompose()

            for el in content.find_all(class_='paywall'):
                el.unwrap()

            for el in content.find_all('figure', class_='optimized-table-widget'):
                el.unwrap()

            for el in content.find_all('table', attrs={"style": False}):
                el['style'] = 'width:100%; border-collapse:collapse;'
                for it in el.find_all('tr'):
                    it['style'] = 'border-bottom:1px solid light-dark(#ccc, #333);'

            for el in content.find_all(class_='wp-block-image'):
                captions = []
                it = el.find('figcaption')
                if it:
                    captions.append(it.decode_contents())
                it = el.find(class_='image-credit')
                if it:
                    captions.append(it.decode_contents())
                it = el.find('img')
                if it and it.get('data-src'):
                    img_src = it['data-src']
                elif it and it.get('src'):
                    img_src = it['src']
                else:
                    img_src = ''
                if img_src:
                    new_html = utils.add_image(img_src, ' | '.join(captions))
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                else:
                    logger.warning('unhandled wp-block-image in ' + item['url'])

            for el in content.find_all(class_='twitter-tweet'):
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)

            for el in content.find_all(class_='tiktok-embed'):
                new_html = utils.add_embed(el['cite'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)

            for el in content.find_all(class_='is-provider-datawrapper'):
                it = el.find('iframe')
                new_html = utils.add_embed(it['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)

            for el in content.find_all(class_='wp-block-pullquote'):
                if el.blockquote:
                    it = el.find('cite')
                    if it:
                        author = it.decode_contents()
                        it.decompose()
                    new_html = utils.add_pullquote(el.blockquote.decode_contents(), author)
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
                else:
                    logger.warning('unhandled wp-block-pullquote in ' + item['url'])

            for el in content.find_all(class_='product-card-inline-wrapper'):
                for it in el.find_all('span', attrs={"data-sheets-value": True}):
                    it.unwrap()
                new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; border: 1px solid light-dark(#ccc, #333); border-radius:10px; padding:8px;">'
                it = el.select('div.card-image img')
                if it:
                    new_html += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%;"></div>'.format(it[0]['src'])
                new_html += '<div style="flex:2; min-width:256px;">'
                it = el.find(class_='card-title')
                if it:
                    new_html += '<div style="font-size:1.1em; font-weight:bold; margin-bottom:8px;">' + it.get_text() + '</div>'
                it = el.find(class_='card-subtitle')
                if it:
                    new_html += '<div>' + it.get_text() + '</div>'
                it = el.find(class_='card-description')
                if it:
                    new_html += it.decode_contents()
                new_html += '</div><div style="flex:2; min-width:256px;">'
                if el.find('section', class_='card-accordion'):
                    for it in el.find_all(class_='card-accordion-panel'):                        
                        label = it.find_previous_sibling('label')
                        new_html += '<details>'
                        if label:
                            new_html += '<summary style="font-size:1.05em; font-weight:bold;">' + label.get_text() + '</summary>'
                        if it.decode_contents().strip().startswith('<'):
                            new_html += it.decode_contents()
                        else:
                            new_html += '<p>' + it.decode_contents().strip() + '</p>'
                        new_html += '</details>'
                it = el.find(class_='button-desktop')
                if it:
                    new_html += utils.add_button(it['href'], it.get_text())                
                new_html += '</div></div>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)

            item['content_html'] += str(content)

        if head_data['pageType'] == 'franchise-list' or head_data['pageType'] == 'edu-rankings-list':
            if article_json.get('intro'):
                item['content_html'] += article_json['intro']
            if article_json.get('description'):
                item['content_html'] += article_json['description']

        if article_json.get('lists'):
            # TODO: can there be multiple galleries?
            item['_gallery'] = []
            for lst in article_json['lists']:
                if lst.get('title'):
                    item['content_html'] += '<h2>' + lst['title'] + '</h2>'
                item['content_html'] += '<h3><a href="{}/gallery?url={}" target="_blank">View as slideshow</a></h3>'.format(config.server, quote_plus(item['url']))
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for it in lst['items']:
                    img_src = it['image']
                    thumb = utils.clean_url(img_src) + '?w=640&q=75'
                    desc = '<h3>'
                    if it.get('rank') and it['rank'] != 0:
                        desc += '{}. '.format(it['rank'])
                    desc += '<a href="{}" target="_blank">{}</a></h3>'.format(it['url'], it['title'])
                    if it.get('content'):
                        if it['content'].startswith('<div'):
                            soup = BeautifulSoup(it['content'], 'html.parser')
                            for el in soup.find_all(class_=['page', 'section', 'layoutArea', 'column']):
                                el.unwrap()
                            desc += str(soup)
                        else:
                            desc += it['content']
                    item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, '', link=img_src, desc=desc) + '</div>'
                    item['_gallery'].append({"src": img_src, "caption": "", "thumb": thumb, "desc": desc})
                item['content_html'] += '</div>'

        if article_json.get('programs'):
            item['_gallery'] = []
            item['content_html'] += '<h3><a href="{}/gallery?url={}" target="_blank">View as slideshow</a></h3>'.format(config.server, quote_plus(item['url']))
            item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            for it in article_json['programs']:
                img_src = it['image']['mediaItemUrl']
                caption = it['image'].get('credit')
                thumb = utils.clean_url(img_src) + '?w=640&q=75'
                desc = '<h3>'
                if it.get('rank') and it['rank'] != 0:
                    desc += '{}. '.format(it['rank'])
                desc += '<a href="https://{}{}" target="_blank">{}</a></h3>'.format(split_url.netloc, it['itemLink'], it['name'])
                desc += '<div style="font-size:0.9em;">' + it['location'] + '</div>'
                if it.get('description'):
                    if it['description'].startswith('<p'):
                        desc += it['description']
                    else:
                        desc += '<p>' + it['description'] + '</p>'
                if it.get('properties'):
                    desc += '<table style="width:100%; border-collapse:collapse;">'
                    for i, prop in enumerate(it['properties']):
                        if i == 0:
                            desc += '<tr>'
                        else:
                            desc += '<tr style="border-top:1px solid light-dark(#ccc, #333);">'
                        desc += '<td style="text-align:left;">{}</td><td style="text-align:right;">{}</td></tr>'.format(prop['name'], prop['value'])
                    desc += '</table>'
                item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src, desc=desc) + '</div>'
                item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})
            item['content_html'] += '</div>'

        if article_json.get('faq'):
            item['content_html'] += '<h2>FAQ</h2>'
            for it in article_json['faq']:
                item['content_html'] += '<h3>{}</h3><p>{}</p>'.format(it['question'], it['answer'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://fortune.com/feed/?tag=datasheet
    if '/feed' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None

    if '/the-latest/' in url:
        articles = next_data['pageProps']['latest']['posts']
        feed_title = next_data['pageProps']['latest']['metaTitle']
    elif '/section/' in url:
        articles = next_data['pageProps']['section']['posts']
        feed_title = next_data['pageProps']['section']['metaTitle']
    else:
        articles = []
        if next_data['pageProps'].get('latestArticles'):
            articles += next_data['pageProps']['latestArticles']
        if next_data['pageProps'].get('features'):
            for it in next_data['pageProps']['features']:
                articles += it['articles']
        if next_data['pageProps'].get('editorsPicks'):
            articles += next_data['pageProps']['editorsPicks']
        if next_data['pageProps'].get('videos'):
            articles += next_data['pageProps']['videos']
        feed_title = next_data['pageProps']['headData']['siteName']

    split_url = urlsplit(url)

    n = 0
    items = []
    for article in articles:
        if article.get('videoId'):
            article_url = 'https://{}/videos/watch/{}'.format(split_url.netloc, article['videoId'])
        else:
            article_url = 'https://{}{}'.format(split_url.netloc, article['titleLink'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
