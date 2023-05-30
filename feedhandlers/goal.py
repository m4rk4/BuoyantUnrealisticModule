import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


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
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    if split_url.netloc == 'assets.goal.com':
        return '{}://{}{}?auto=webp&format=pjpg&width={}&quality=60'.format(split_url.scheme, split_url.netloc, split_url.path, width)
    return img_src


def add_fcplayer_video(video_src, split_url, page_layer):
    m = re.search(r'\#([A-Z]+)_([0-9a-f\-]+)', video_src)
    if m:
        if m.group(1) == 'SEMANTIC':
            player_url = 'https://fcp-api.footballco.cloud/v1/public/semantic-article?tags='
            if page_layer.get('primaryTagName'):
                player_url += quote(page_layer['primaryTagName'])
            if page_layer.get('secondaryTagName'):
                player_url += ',' + quote(page_layer['secondaryTagName'])
            if page_layer.get('otherContentTags'):
                for it in page_layer['otherContentTags']:
                    player_url += ',' + quote(it)
            player_url += '&url={}{}&embedCode={}&domain={}'.format(split_url.netloc, split_url.path, m.group(2), split_url.netloc.replace('www.', ''))
        elif m.group(1) == 'SINGLE':
            player_url = 'https://fcp-api.footballco.cloud/v1/public/embed/embed-code-videos/{}?domain=goal.com'.format(m.group(2))
        #print(player_url)
        for i in range(3):
            player_json = utils.get_url_json(player_url)
            if player_json:
                #print(player_json['mediaItems'][0]['media_id'])
                args = {
                    "data-video-id": player_json['mediaItems'][0]['media_id'],
                    "data-account": 6286608028001,
                    "data-key": "BCpkADawqM0lCsAWcGMZHp9i0FDZuXOz84V9bT5n2whHerNqm7Cu4BHvqt45Q-5EM3haOuEM46vnArXit-ydAG3olY3hbWekqw-5GBymX4WDPEXJcjnL_S8cWwiFnAHBeFO8-n_b_N6_RwRL"
                }
                video_url = 'https://edge.api.brightcove.com/playback/v1/accounts/6286608028001/videos/{}'.format(player_json['mediaItems'][0]['media_id'])
                return utils.add_embed(video_url, args)
    return ''

def format_body(body, url, page_layer):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    soup = BeautifulSoup(body['body'], 'html.parser')
    for el in soup.find_all('script'):
        if el.get('data-placement'):
            if el['data-placement'] == 'betting-e2' or el['data-placement'] == 'mobile-advert':
                el.decompose()
            elif el['data-placement'] == 'poll':
                data = body['embeds']['poll']
                new_html = '<hr/><div style="width:80%; margin-right:auto; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; padding:10px;"><h2>Poll: {}</h2>'.format(data['question'])
                for it in data['answers']['options']:
                    pct = int(it['numberOfVotes'] / data['answers']['numberOfVotes'] * 100)
                    if pct >= 50:
                        new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p>{}</p><p>{}%</p></div>'.format(pct, 100 - pct, it['name'], pct)
                    else:
                        new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p>{}</p><p>{}%</p></div>'.format(100 - pct, pct, it['name'], pct)
                new_html += '<div><small>{} votes</small></div></div>'.format(data['answers']['numberOfVotes'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            elif el['data-placement'] == 'editors-picks':
                data = json.loads(el.string)
                new_html = '<hr/><h2>Editors\' Picks</h2><ul>'
                for it in data['data']['editorsPicks']:
                    new_html += '<li><a href="{}://{}/{}/{}/{}">{}</a></li>'.format(split_url.scheme, split_url.netloc, '/'.join(paths[:-2]), it['slug'], it['id'], it['headline'])
                new_html += '</ul>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            elif el['data-placement'] == 'fcplayer-semantic':
                data = json.loads(el.string)
                new_html = add_fcplayer_video(data['data']['embedCode'], split_url, page_layer)
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled fcplayer-semantic script in ' + url)
            else:
                logger.warning('unhandled {} script in {}'.format(el['data-placement'], url))
        else:
            el.decompose()

    for el in soup.find_all('table'):
        el['style'] = 'width:100%;'
        for it in el.find_all('th'):
            it['style'] = 'text-align:left;'

    for el in soup.find_all('picture'):
        it = el.find('img')
        if it:
            if it.get('data-source'):
                caption = it['data-source'].strip()
            elif it.get('data-copyright'):
                caption = it['data-copyright'].strip()
            else:
                caption = ''
            new_html = utils.add_image(resize_image(it['src']), caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('iframe'):
        if 'stake.us' not in el['src']:
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('blockquote', class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('blockquote', class_='instagram-media'):
        new_html = utils.add_embed(el['data-instgrm-permalink'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'center':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    return str(soup)


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    slides = None
    if next_data['pageProps']['content'].get('article'):
        article_json = next_data['pageProps']['content']['article']
    elif next_data['pageProps']['content'].get('slideList'):
        article_json = next_data['pageProps']['content']['slideList']['article']
        slides = next_data['pageProps']['content']['slideList']['slides']
    elif next_data['pageProps']['content'].get('liveBlog'):
        article_json = next_data['pageProps']['content']['liveBlog']

    page_layer = next_data['pageProps']['page']['data']['layer']

    item = {}
    item['id'] = article_json['id']
    item['url'] = next_data['pageProps']['page']['meta']['seo']['canonicalUrl']
    item['title'] = article_json['headline']

    #dt = datetime.fromisoformat(article_json['publishTime'].replace('Z', '+00:00'))
    dt = datetime.fromisoformat(page_layer['firstPublishTime'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(page_layer['lastPublishTime'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('author'):
        authors = []
        for it in article_json['author']:
            authors.append(it['name'])
        if authors:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'GOAL'

    if article_json.get('tagList') and article_json['tagList'].get('tags'):
        item['tags'] = []
        for it in article_json['tagList']['tags']:
            item['tags'].append(it['name'])

    if article_json.get('teaser'):
        item['summary'] = article_json['teaser']

    item['content_html'] = ''
    if article_json.get('match'):
        item['content_html'] += '<table style="width:100%"><tr>'
        item['content_html'] += '<td style="text-align:center; vertical-align:middle;"><img src="{}" style="width:60px;"/><br/><b>{}</b></td>'.format(article_json['match']['teamA']['crest']['url'], article_json['match']['teamA']['name'])
        tz_loc = pytz.timezone(config.local_tz)
        dt = datetime.fromisoformat(article_json['match']['startDate'].replace('Z', '+00:00')).astimezone(tz_loc)
        item['content_html'] += '<td style="text-align:center; vertical-align:middle;"><small>{}</small><br/><span style="font-size:1.2em; font-weight:bold;">{}:{}</span></td>'.format(utils.format_display_date(dt, False), dt.hour, dt.minute)
        item['content_html'] += '<td style="text-align:center; vertical-align:middle;"><img src="{}" style="width:60px;"/><br/><b>{}</b></td>'.format(article_json['match']['teamB']['crest']['url'], article_json['match']['teamB']['name'])
        item['content_html'] += '</tr></table><div>&nbsp;</div>'

    if article_json.get('poster'):
        if article_json['poster'].get('image'):
            item['_image'] = resize_image(article_json['poster']['image']['src'])
        if article_json['poster']['type'] == 'Image':
            if article_json['poster'].get('credit'):
                caption = article_json['poster']['credit']
            elif article_json['poster'].get('source'):
                caption = article_json['poster']['source']
            else:
                caption = ''
            item['content_html'] += utils.add_image(item['_image'], caption)
        elif article_json['poster']['type'] == 'YoutubeVideo':
            soup = BeautifulSoup(article_json['poster']['embed'], 'html.parser')
            item['content_html'] += utils.add_embed(soup.iframe['src'])
        elif article_json['poster']['type'] == 'FCPlayerVideo':
            soup = BeautifulSoup(article_json['poster']['embed'], 'html.parser')
            item['content_html'] += add_fcplayer_video(soup.script['src'], urlsplit(url), page_layer)
        else:
            logger.warning('unhandled poster media type {} in {}'.format(article_json['poster']['type'], item['url']))

    if article_json.get('body'):
        item['content_html'] += format_body(article_json['body'], item['url'], page_layer)

    if article_json.get('pinned'):
        item['content_html'] += '<h2>Summary</h2><ul>'
        for post in article_json['pinned']:
            item['content_html'] += '<li>{}</li>'.format(post['headline'])
        item['content_html'] += '</ul>'

    if article_json.get('posts'):
        for post in article_json['posts']:
            #print(post['id'])
            dt = datetime.fromisoformat(post['updateTime'].replace('Z', '+00:00'))
            item['content_html'] += '<hr/><div>{}</div><h2>{}</h2>'.format(utils.format_display_date(dt), post['headline'])
            if post.get('media'):
                if post['media']['type'] == 'Image':
                    if post['media'].get('credit'):
                        caption = post['media']['credit']
                    elif post['media'].get('source'):
                        caption = post['media']['source']
                    else:
                        caption = ''
                    item['content_html'] += utils.add_image(resize_image(post['media']['image']['src']), caption)
                elif post['media']['type'] == 'YoutubeVideo':
                    soup = BeautifulSoup(post['media']['embed'], 'html.parser')
                    item['content_html'] += utils.add_embed(soup.iframe['src'])
                else:
                    logger.warning('unhandled post media type {} in {}'.format(post['media']['type'], item['url']))
            if post.get('details'):
                item['content_html'] += format_body(post['details'], item['url'], page_layer)

    if slides:
        for slide in slides:
            item['content_html'] += '<hr/>'
            if slide.get('media'):
                if slide['media']['type'] == 'Image':
                    if slide['media'].get('credit'):
                        caption = slide['media']['credit']
                    elif slide['media'].get('source'):
                        caption = slide['media']['source']
                    else:
                        caption = ''
                    item['content_html'] += utils.add_image(resize_image(slide['media']['image']['src']), caption)
                elif post['media']['type'] == 'YoutubeVideo':
                    soup = BeautifulSoup(slide['media']['embed'], 'html.parser')
                    item['content_html'] += utils.add_embed(soup.iframe['src'])
                else:
                    logger.warning('unhandled slide media type {} in {}'.format(slide['media']['type'], item['url']))
            slide_body = format_body(slide['body'], item['url'], page_layer)
            item['content_html'] += '<h3>{}</h3>{}'.format(slide['headline'], slide_body)

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    n = 0
    feed_items = []
    feed_title = ''

    if paths[-1] == 'news':
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        for article in next_data['pageProps']['content']['newsArchive']['news']['cards']:
            article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['url'])
            if next((it for it in feed_items if it['url'] == article_url), None):
                continue
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
        feed_title = next_data['pageProps']['page']['meta']['seo']['title']
    else:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        for el in soup.find_all(attrs={"data-side": "link"}):
            article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, el['href'])
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
        el = soup.find('meta', attrs={"property": "og:title"})
        if el:
            feed_title = el['content']
        else:
            el = soup.find('title')
            if el:
                feed_title = el.get_text()

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
