import base64, json, pytz, re, secrets
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_img_src(link_href):
    if link_href.startswith('cs:///'):
        img_src = link_href.replace('cs:///', 'https://www.edmunds.com/assets/m/cs/')
    elif link_href.startswith('dam:///photo'):
        img_src = link_href.replace('dam:///photo', 'https://media.ed.edmunds-media.com')
    elif link_href.startswith('//'):
        img_src = 'https:' + link_href
    elif link_href.startswith('/'):
        img_src = 'https://media.ed.edmunds-media.com' + link_href
    else:
        img_src = link_href
    if not re.search(r'\.(jpg|png)$', img_src, flags=re.I):
        img_src += '_1600.jpg'
    else:
        img_src = re.sub('_717\.jpg', '_1600.jpg', img_src, flags=re.I)
    return img_src


def add_photo(entry):
    photo_html = ''
    for link in entry['links']:
        captions = []
        if link.get('title'):
            captions.append(link['title'])
        if link.get('author'):
            captions.append(link['author'])
        img_src = get_img_src(link['href'])
        photo_html += utils.add_image(img_src, ' | '.join(captions))
    return photo_html


def get_stock_photo(make, model, year):
    page_html = utils.get_url_html('https://www.edmunds.com/{}/{}/{}'.format(make.lower().replace(' ', '-'), model.lower().replace(' ', '-'), year))
    if page_html:
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            return el['content']
    return ''


def format_entry(entry):
    entry_html = ''
    if entry['id'].startswith('html'):
        if entry['content'].startswith('<'):
            soup = BeautifulSoup(entry['content'], 'html.parser')
            for el in soup.find_all(['script', 'style']):
                el.decompose()
            for el in soup.find_all('img'):
                img_src = get_img_src(el['src'])
                new_html = utils.add_image(img_src)
                new_el = BeautifulSoup(new_html, 'html.parser')
                if el.parent and el.parent.name == 'p' and not el.parent.get_text().strip():
                    el.parent.insert_after(new_el)
                    el.parent.decompose()
                else:
                    el.insert_after(new_el)
                    el.decompose()
            entry_html += str(soup)
        else:
            entry_html += '<p>{}</p>'.format(entry['content'])
    elif entry['id'].startswith('photo'):
        if entry.get('links'):
            entry_html += add_photo(entry)
    elif entry['id'] == 'hero-content':
        if entry['contentMetadata'].get('type'):
            if entry['contentMetadata']['type'] == 'photo':
                entry_html += add_photo(entry)
            else:
                logger.warning('unhandled here-content entry type {}'.format(entry['contentMetadata']['type']))
    elif entry['id'] == 'info-graphic' and entry['contentMetadata'].get('media-image'):
        entry_html += utils.add_image(get_img_src(entry['contentMetadata']['media-image']))
    elif (entry['id'].startswith('video') or entry['id'] == 'highlight-video') and entry['id'] != 'video-ad':
        if entry['contentMetadata'].get('type'):
            if entry['contentMetadata']['type'] == 'youtube':
                if entry['contentMetadata'].get('youtube-videoid'):
                    entry_html += utils.add_embed('https://www.youtube.com/watch?v={}'.format(entry['contentMetadata']['youtube-videoid']))
                elif entry['contentMetadata'].get('videoId'):
                    entry_html += utils.add_embed('https://www.youtube.com/watch?v={}'.format(entry['contentMetadata']['videoId']))
                else:
                    logger.warning('unknown youtube video id')
            else:
                logger.warning('unhandled video entry type {}'.format(entry['contentMetadata']['type']))
    elif entry['id'].startswith('faq'):
        if entry.get('title'):
            entry_html += '<h2>{}</h2>'.format(entry['title'])
        if entry.get('childEntries'):
            for child in entry['childEntries']:
                entry_html += format_entry(child)
    elif entry['id'].startswith('qanda'):
        entry_html += '<dl><dt style="font-size:1.1em;"><b>{}</b></dt><dd>{}</dd></dl>'.format(entry['contentMetadata']['question'], entry['contentMetadata']['answer'])
    elif entry['id'].startswith('table'):
        entry_html += '<table style="border-collapse:collapse; border:1px solid black;"><tr style="background-color:rgba(0, 126, 229, 0.2);">'
        for i in range(int(entry['contentMetadata']['columnCount'])):
            entry_html += '<th style="border-collapse:collapse;">{}</th>'.format(entry['contentMetadata']['columnHeader{}'.format(i + 1)])
        entry_html += '</tr>'
        for i in range(int(entry['contentMetadata']['rowCount'])):
            if i % 2:
                entry_html += '<tr style="background-color:lightgrey;">'
            else:
                entry_html += '<tr style="background-color:white;">'
            values = entry['contentMetadata']['row{}Values'.format(i + 1)].split('|')
            for val in values:
                entry_html += '<td style="border-collapse:collapse; padding:4px;">{}</td>'.format(val)
            entry_html += '</tr>'
        entry_html += '</table>'
    elif entry['id'] == 'compare':
        entry_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        compare_link = 'https://www.edmunds.com/car-comparisons/?'
        for i, link in enumerate(entry['links']):
            img_src = get_img_src(link['href'])
            vehicle = entry['vehicles'][i]
            title = '{} {} {}'.format(vehicle['year'], vehicle['make'], vehicle['model'])
            href = 'https://www.edmunds.com/{}/{}/{}/null/'.format(vehicle['make'].lower().replace(' ', '-'), vehicle['model'].lower().replace(' ', '-'), vehicle['year'])
            entry_html += '<div style="flex:1; min-width:200px; max-width:256px;"><a href="{}"><img src="{}" style="width:100%;" /><div style="text-align:center;">{}</div></a></div>'.format(href, img_src, title)
            compare_link += 'veh{}={}|null&'.format(i+1, vehicle['style'])
        entry_html += '</div>'
        entry_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#1a854a; padding:0.5em;">{}</span></a></div>'.format(compare_link[:-1], entry['contentMetadata']['buttonText'])
    elif entry['id'] == 'main':
        if entry.get('childEntries'):
            for child in entry['childEntries']:
                entry_html += format_entry(child)
    elif entry['id'].startswith('section-'):
        if entry['contentMetadata'].get('title'):
            entry_html += '<{0}>{1}</{0}>'.format(entry['contentMetadata']['titleTag'], entry['contentMetadata']['title'])
        if entry.get('childEntries'):
            for child in entry['childEntries']:
                entry_html += format_entry(child)
    elif entry['id'].startswith('card-header-'):
        if entry['contentMetadata'].get('card-title'):
            entry_html += '<h2>{}</h2>'.format(entry['contentMetadata']['card-title'])
        if entry.get('childEntries'):
            for child in entry['childEntries']:
                entry_html += format_entry(child)
    elif entry['id'].startswith('vehicle-card-'):
        if entry['contentMetadata'].get('ranking'):
            ranking = '#{}. '.format(entry['contentMetadata']['ranking'])
        else:
            ranking = ''
        if entry.get('childEntries'):
            entry_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; padding:8px; border:1px solid black; border-radius:10px;">'
            child = next((it for it in entry['childEntries'] if it and it['id'] == 'vehicle-title'), None)
            if child:
                vehicle_url = 'https://www.edmunds.com{}' + child['contentMetadata']['vehicle-url']
                vehicle_title = child['contentMetadata']['vehicle-title']
            child = next((it for it in entry['childEntries'] if it and it['id'] == 'photo'), None)
            if child:
                vehicle = child['vehicles'][0]
                img_src = get_stock_photo(vehicle_url)
                if img_src:
                    href = 'https://www.edmunds.com/{}/{}/{}/'.format(vehicle['make'].lower().replace(' ', '-'), vehicle['model'].lower().replace(' ', '-'), vehicle['year'])
                    entry_html += '<div style="flex:1; min-width:240px;"><a href="{}"><img src="{}" style="width:100%;" /></a></div>'.format(href, img_src)
            entry_html += '<div style="flex:1; min-width:240px;">'
            entry_html += '<div style="font-size:1.1em; font-weight:bold;">{}<a href="https://www.edmunds.com{}">{}</a></div>'.format(ranking, vehicle_url, vehicle_title)
            child = next((it for it in entry['childEntries'] if it and it['id'] == 'vehicle-content'), None)
            if child:
                entry_html += '<p>{}</p>'.format(child['contentMetadata']['text'])
            child = next((it for it in entry['childEntries'] if it and it['id'] == 'card-buttons'), None)
            if child:
                n = 0
                for key in child['contentMetadata'].keys():
                    if key.endswith('-title'):
                        n += 1
                for i in range(1, n+1):
                    entry_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="https://www.edmunds.com{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#1a854a; padding:0.5em;">{}</span></a></div>'.format(child['contentMetadata']['button{}-url'.format(i)], child['contentMetadata']['button{}-title'.format(i)])
            entry_html += '</div>'
            child = next((it for it in entry['childEntries'] if it and it['id'] == 'vehicle-data-points'), None)
            if child:
                n = 0
                for key in child['contentMetadata'].keys():
                    if key.startswith('data-title'):
                        n += 1
                if n > 0:
                    entry_html += '<div style="flex:1; min-width:240px;"><dl>'
                    for i in range(1, n+1):
                        if child['contentMetadata'].get('data-title-{}'.format(i)):
                            entry_html += '<dt><small>{}</small></dt>'.format(child['contentMetadata']['data-title-{}'.format(i)])
                        if child['contentMetadata'].get('data-value-{}'.format(i)):
                            entry_html += '<dd><b>{}</b></dd>'.format(child['contentMetadata']['data-value-{}'.format(i)])
                    entry_html += '</dl></div>'
            entry_html += '</div><div>&nbsp;</div>'
    elif entry['id'].startswith('shopping-link'):
        entry_html = utils.add_blockquote('<div><a href="https://www.edmunds.com{}"><b>{}</b></a></div><div>{}</div>'.format(entry['contentMetadata']['url'], entry['contentMetadata']['label'], entry['contentMetadata']['description']))
    elif entry['id'].endswith('-ad') or entry['id'].endswith('-links') or entry['id'].endswith('-module') or entry['id'].endswith('-rail') or entry['id'] == 'config' or entry['id'] == 'editorial-high-impact' or entry['id'] == 'footer' or entry['id'] == 'internal' or entry['id'] == 'related-articles-links-from-config' or entry['id'] == 'subnav' or entry['id'] == 'vehicle-testing-team':
        pass
    else:
        logger.warning('unhandled {} entry'.format(entry['id']))
    return entry_html


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile('window\.__PRELOADED_STATE__\s?='))
    if not el:
        logger.warning('unable to find window.__PRELOADED_STATE__ in ' + url)
        return None

    i = el.string.find('{')
    j = el.string.rfind('}')
    preload_state = json.loads(el.string[i:j+1])
    if save_debug:
        utils.write_file(preload_state, './debug/debug.json')

    content_json = None
    if preload_state['cms'].get('content'):
        for key, val in preload_state['cms']['content'].items():
            if isinstance(val, dict):
                if val.get('contentTypePath') and val['contentTypePath'] == '/editorial/templates/article':
                    content_json = val
                    break
    if not content_json:
        logger.warning('unable to determine content for ' + url)
        return None

    jsonld = preload_state['seo']['headContent']['jsonld']
    article_json = next((it for it in jsonld if it and it['@type'] == 'Article'), None)

    item = {}
    item['id'] = content_json['id']
    if content_json['contentMetadata']['canonical'].startswith('/'):
        split_url = urlsplit(url)
        item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, content_json['contentMetadata']['canonical'])
    else:
        item['url'] = content_json['contentMetadata']['canonical']
    item['title'] = content_json['title']

    # if item['id'].endswith('index'):
    #     logger.warning('skipping ' + item['url'])
    #     return None

    # Not sure what the proper timezone is
    tz = pytz.timezone(config.local_tz)
    dt = datetime.fromisoformat(content_json['published'])
    dt_utc = tz.localize(dt).astimezone(pytz.utc)
    item['date_published'] = dt_utc.isoformat()
    item['_timestamp'] = dt_utc.timestamp()
    item['_display_date'] = utils.format_display_date(dt_utc)
    dt = datetime.fromisoformat(content_json['updated'])
    dt_utc = tz.localize(dt).astimezone(pytz.utc)
    item['date_modified'] = dt_utc.isoformat()

    item['author'] = {}
    authors = []
    if content_json.get('authors'):
        for it in content_json['authors']:
            authors.append(it['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json and article_json.get('author'):
        item['author'] = {"name": article_json['author']['name']}

    if content_json.get('categories'):
        item['tags'] = content_json['categories'].copy()
    elif article_json and article_json.get('keywords'):
        item['tags'] = [it.strip() for it in article_json['keywords'].split(',')]

    if content_json.get('summary'):
        item['summary'] = content_json['summary']
    elif preload_state['seo']['headContent'].get('description'):
        item['summary'] = preload_state['seo']['headContent']['description']

    item['content_html'] = ''
    if content_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(content_json['subtitle'])

    for entry in content_json['childEntries']:
        item['content_html'] += format_entry(entry)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])

    if False:
        # The api call doesn't work with out proper headers
        split_url = urlsplit(url)
        path = split_url.path.replace('.html', '')
        content_url = 'https://www.edmunds.com/gateway/api/editorial/v3/content/?path=/research/best{0},/research{0},{0}&fetchcontents=true&ispreview=true&tree=true&externalfetch=true'.format(path)
        print(content_url)
        loader_config = {
            "accountID": "3086065",
            "trustKey": "3086065",
            "agentID": "455949525",
            "licenseKey": "NRJS-5c12aac231d2900133a",
            "applicationID": "455949525"
        }
        span_id = secrets.token_hex(8)
        trace_id = secrets.token_hex(16)
        ts = round(datetime.now().timestamp()*1000)
        tracestate = '{}@nr={}-{}-{}-{}-{}-{}-{}-{}-{}'.format(loader_config['trustKey'], 0, 1, loader_config['accountID'], loader_config['agentID'], span_id, '', '', '', ts)
        traceparent = '00-{}-{}-01'.format(trace_id, span_id)
        c = {
            "v": [
                0,
                1
            ],
            "d": {
                "ty": "Browser",
                "ac": loader_config['accountID'],
                "ap": loader_config['agentID'],
                "id": span_id,
                "tr": trace_id,
                "ti": ts
            }
        }
        newrelic = base64.b64encode(json.dumps(c, separators=(',', ':')).encode('utf-8')).decode('utf-8')
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "newrelic": newrelic,
            "pragma": "no-cache",
            "sec-ch-ua": "\"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"114\", \"Microsoft Edge\";v=\"114\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "traceparent": traceparent,
            "tracestate": tracestate,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.58",
            "x-artifact-id": "venom",
            "x-artifact-version": preload_state['venomVersion']['version'],
            "x-client-action-name": "advice_car_news_article.content",
            "x-deadline": str(round(datetime.now().timestamp()*1000) + 800),
            "x-edw-page-cat": "advice",
            "x-edw-page-name": "advice_car_news_article",
            "x-referer": "https://www.edmunds.com/car-news/epa-filings-reveal-rivian-r1s-dual-motor-range.html",
            "x-trace-id": preload_state['xHeaders']['x-trace-id'],
            "x-trace-seq": preload_state['xHeaders']['x-trace-seq']
        }
        content_json = utils.get_url_json(content_url, headers=headers)
        if not content_json:
            logger.warning('empty content')
            return None
        if save_debug:
            utils.write_file(content_json, './debug/debug.json')

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
