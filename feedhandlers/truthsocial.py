import cloudscraper, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)

def get_redirect_url(url):
    if 'links.truthsocial.com' in url:
        scraper = cloudscraper.create_scraper()
        r = scraper.get(url, allow_redirects=False)
        if r.is_redirect and 'redirected' in r.text:
            soup = BeautifulSoup(r.text, 'lxml')
            el = soup.find('a')
            if el:
                return el['href']
    return url


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'embed' in paths:
        post_id = paths[1]
    elif 'posts' in paths:
        post_id = paths[2]
    else:
        logger.warning('unhandled url ' + url)
        return None
    api_url = 'https://truthsocial.com/api/v1/statuses/' + post_id
    scraper = cloudscraper.create_scraper()
    r = scraper.get(api_url)
    if r.status_code != 200:
        logger.warning('status code {} getting {}'.format(r.status_code, api_url))
        return None
    api_json = json.loads(r.text)
    return get_post(api_json, args, site_json, save_debug)


def get_post(post_json, args, site_json, save_debug=False):
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['url']
    #item['title'] =

    dt = datetime.fromisoformat(post_json['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    time = '{}:{} {}'.format(dt.strftime('%I').lstrip('0'), dt.minute, dt.strftime('%p'))
    date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {"name": post_json['account']['display_name']}

    if post_json.get('tags'):
        item['tags'] = []
        for it in post_json['tags']:
            item['tags'].append(it['name'])

    item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px;">'
    if post_json.get('reblog'):
        item['content_html'] += '<tr><td colspan="2"><small>&#128257;&nbsp;<a style="text-decoration:none;" href="https://truthsocial.com/@{}">@{}</a> ReTruthed</small></td></tr>'.format(post_json['account']['username'], post_json['account']['display_name'])
        post_json = post_json['reblog']

    avatar = '{}/image?url={}&width=48&height=48&mask=ellipse'.format(config.server, quote_plus(post_json['account']['avatar']))
    if post_json['account']['verified'] == True:
        verified_icon = ' &#9989;'
    else:
        verified_icon = ''
    item['content_html'] += '<tr><td style="width:56px;"><img src="{0}" /></td><td><a style="text-decoration:none;" href="https://truthsocial.com/@{1}"><b>{2}</b>{3}<br /><small>@{1}</small></a></td></tr>'.format(avatar, post_json['account']['username'], post_json['account']['display_name'], verified_icon)

    links = {}
    if post_json.get('content') and post_json['content'] != '<p></p>':
        content_soup = BeautifulSoup(post_json['content'], 'html.parser')
        for el in content_soup.find_all('a'):
            if 'links.truthsocial.com' in el['href']:
                link = get_redirect_url(el['href'])
                links[el['href']] = link
                el['href'] = link
            for it in el.find_all(class_='invisible'):
                it.decompose()
            for it in el.find_all(class_='ellipsis'):
                it.string += '…'
        #item['content_html'] += '<tr><td colspan="2" style="padding:0;">{}</td></tr>'.format(post_json['content'])
        item['content_html'] += '<tr><td colspan="2" style="padding:0;">{}</td></tr>'.format(str(content_soup))

    card_html = ''
    if post_json.get('card'):
        if post_json['card']['type'] == 'video' and 'Rumble' in post_json['card']['provider_name']:
            m = re.search(r'src="([^"]+)"', post_json['card']['html'])
            if m:
                if post_json.get('media_attachments') and next((it for it in post_json['media_attachments'] if (it['type'] == 'video' and it.get('external_video_id') and it['external_video_id'] in m.group(1))), None):
                    # Add as media attachment
                    card_html = 'media'
                else:
                    video_content = utils.get_content(m.group(1), {}, False)
                    if video_content:
                        if post_json['card']['url'] in links:
                            link = links[post_json['card']['url']]
                        else:
                            link = get_redirect_url(post_json['card']['url'])
                        poster = '{}/image?width=500&url={}&overlay=video'.format(config.server, quote_plus(video_content['_image']))
                        card_html += '<div style="border:1px solid black; border-radius:10px;"><div><a href="{}"><img style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" src="{}" /></a></div>'.format(video_content['_video'], poster)
                        if post_json['card'].get('title'):
                            card_html += '<div style="font-weight:bold; padding-bottom:8px; padding:0 0.5em 0.5em 0.5em;"><a href="{}">{}</a></div>'.format(link, post_json['card']['title'])
                        card_html += '<div style="font-size:0.9em; padding:0 0.5em 0.5em 0.5em;">🔗 {}</div></div>'.format(post_json['card']['provider_name'])
        elif post_json['card']['type'] == 'link':
            if post_json['card']['url'] in links:
                link = links[post_json['card']['url']]
            else:
                link = get_redirect_url(post_json['card']['url'])
            card_html = '<div style="border:1px solid black; border-radius:10px;">'
            if post_json['card'].get('image'):
                card_html += '<div><a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a></div>'.format(link, post_json['card']['image'])
            card_html += '<div style="font-weight:bold; padding-bottom:8px; padding:0 0.5em 0.5em 0.5em;"><a href="{}">{}</a></div>'.format(link, post_json['card']['title'])
            if post_json['card'].get('description'):
                card_html += '<div style="font-size:0.95em; padding:0 0.5em 0.5em 0.5em;">{}</div>'.format(post_json['card']['description'])
            card_html += '<div style="font-size:0.9em; padding:0 0.5em 0.5em 0.5em;">🔗 {}</div>'.format(post_json['card']['provider_name'])
            card_html += '</div>'
        if card_html:
            if card_html != 'media':
                item['content_html'] += '<tr><td colspan="2" style="padding:0;">' + card_html + '</td></tr>'
        else:
            logger.warning('unhandled card type {} in {}'.format(post_json['card']['type'], item['url']))

    if post_json.get('media_attachments'):
        item['content_html'] += '<tr><td colspan="2" style="padding:0;">'
        n = len(post_json['media_attachments']) - 1
        for i, media in enumerate(post_json['media_attachments']):
            media_html = ''
            if media['type'] == 'image':
                media_html += '<div><a href="{0}"><img width="100%" style="border-radius:10px" src="{0}" /></a></div>'.format(media['url'])
            elif media['type'] == 'video' and media.get('external_video_id'):
                video_content = utils.get_content('https://rumble.com/embed/{}/'.format(media['external_video_id']), {}, False)
                if video_content:
                    poster = '{}/image?width=500&url={}&overlay=video'.format(config.server, quote_plus(video_content['_image']))
                    media_html += '<div><a href="{}"><img width="100%" style="border-radius:10px" src="{}" /></a></div>'.format(video_content['_video'], poster)
            if media_html:
                item['content_html'] += media_html
                if i < n:
                    item['content_html'] += '<div>&nbsp;</div>'
            else:
                logger.warning('unhandled media type {} in {}'.format(media['type'], item['url']))
        item['content_html'] += '</td></tr>'

    item['content_html'] += '<tr><td colspan="2"><a style="text-decoration:none;" href="{}"><small>{} · {}</small></a></td></tr></table>'.format(item['url'], time, date)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0 or len(paths) > 1:
        logger.warning('unhandled url ' + url)
        return None

    scraper = cloudscraper.create_scraper()
    api_url = 'https://truthsocial.com/api/v1/accounts/lookup?acct=' + paths[0][1:]
    r = scraper.get(api_url)
    if r.status_code != 200:
        logger.warning('status code {} getting {}'.format(r.status_code, api_url))
        return None
    api_json = json.loads(r.text)
    api_url = 'https://truthsocial.com/api/v1/accounts/{}/statuses?exclude_replies=true&with_muted=true'.format(api_json['id'])
    r = scraper.get(api_url)
    if r.status_code != 200:
        logger.warning('status code {} getting {}'.format(r.status_code, api_url))
        return None
    api_json = json.loads(r.text)
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for post in api_json:
        post_url = 'https://truthsocial.com/@{}/status/{}'.format(post['account']['username'], post['id'])
        if save_debug:
            logger.debug('getting content for ' + post_url)
        item = get_post(post, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = '{} | Truth Social'.format(paths[0])
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed