import json, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        path += '.json'
    next_url = '{}://{}/_next/data/{}/en-US{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False, data_json=None):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    # https://www.sportsgrid.com/_next/static/chunks/pages/_app-17144cbd9d77ee3c.js
    # re.search(r'AUTHORIZATION_TOKEN:"([^"]+)', page_html)
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIxIiwianRpIjoiMTdkMzE0MzFmYTU3MjVhY2YzMDg0NzIxMjVkMzg2OGY4MmQ5YTUwMWVjZDM1YmNiZGQwYzAxNzM0ZGI0ZTFhODU3OGJmNzc5NzEyMDcyODkiLCJpYXQiOjE2ODkxNjk1NzAuMjE2NTI0LCJuYmYiOjE2ODkxNjk1NzAuMjE2NTI2LCJleHAiOjE3MjA3OTE5NzAuMjEzODg0LCJzdWIiOiIxNjEyIiwic2NvcGVzIjpbXX0.FJYBCYgShPgAeOsRbpbrEMTMV13Mp7SDlXJV8mnngaW1iesHYedMv07H6w4qpzJ6wbYPVRun9qjD8RqNYlc7dHa7vFLT1bUNHSWdfRepxV20-jzmC0hC1IKLMwG94QgvT-T6-8vH6zEWAFOcnX6UuffzoKIJ7H-Pz859YeECDCD1fjdI1dS7MB5-1mqTohmBf-JrCm5wRL2yd5IbDu_BR90v_VZ6CoxEVBzAj0_BQnmPtjalf6OPsjc2eJ2iztYf06WyiX2gDpDhQXhUVqku9q7zVQNme0043VHIZSVMDsZ-G3RY0b2CkREINAPeW-PKzUk80j2wf5TWiBkgMDVYyuy5BId_UavvYnG7oNseeMcmcanzkeIkb1bqkpzok35-K9-zbZ4q6cyLWe8Xhkx8a0epUJ7KEy3ROwaMRLr6MYbadioj2JPgETC7NNia5vhQSz1iTkygBfvQiPaNNVMV4-MIbiGvgfgWkiud3tA7DLrSm8DpuA51--vx1EzQw35Gs3KDfJr9M-Nu69iOybeT44__OnRu1QjntgmlgJKN4b30qq4wYB8hyzusprxAlqFN4tYkOhQQCtEP5fu2dGqpWFZiZj9RFuKb2yvaKaBl70L0Vw-BMj8PLevsHTHRXVbPNANWY0NrL2O1QlfHHDn-AUE-LsFlue-yudX5_u8KhoE",
        "content-type": "application/json",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Not A(Brand\";v=\"8\", \"Chromium\";v=\"132\", \"Microsoft Edge\";v=\"132\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }

    if not data_json:
        if 'article' in paths:
            api_url = 'https://web.sportsgrid.com/api/web/v1/getArticleData'
            api_data = {
                "sport": paths[0],
                "slug": paths[-1]
            }
            data_key = 'article_data'
        elif 'video' in paths:
            api_url = 'https://web.sportsgrid.com/api/web/v1/getVideoData'
            api_data = {
                "sport": paths[0],
                "slug": paths[-1]
            }
            data_key = 'video_data'
        elif 'shorts' in paths:
            api_url = 'https://web.sportsgrid.com/api/web/v1/getShorts'
            api_data = {
                "slug": paths[-1]
            }
            data_key = 'data'

        api_json = utils.post_url(api_url, json_data=api_data, headers=headers)
        if not api_data:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/debug.json')

        if api_json['data'].get('redirectTo'):
            redirect_url = 'https://www.sportsgrid.com/' + api_json['data']['redirectTo']
            logger.debug('redirecting to ' + redirect_url)
            return get_content(redirect_url, args,site_json, save_debug)

        data_json = api_json['data'][data_key]
        if isinstance(data_json, list):
            data_json = data_json[0]

    item = {}
    item['id'] = data_json['id']

    if data_json.get('canonical_url'):
        item['url'] = data_json['canonical_url']
    elif data_json.get('share_url'):
        item['url'] = data_json['share_url']
    else:
        item['url'] = url

    item['title'] = data_json['title']

    # TODO: timezone?
    dt = dateutil.parser.parse(data_json['published_date']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if data_json.get('modified_date'):
        dt = dateutil.parser.parse(data_json['modified_date']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    if data_json.get('author_title'):
        item['author'] = {
            "name": data_json['author_title']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    elif data_json.get('talent'):
        if isinstance(data_json['talent'], list):
            item['authors'] = [{"name": x['title']} for x in data_json['talent']]
        else:
            item['authors'] = [{"name": x} for x in data_json['talent'].values()]
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
    elif data_json.get('ep_show_name'):
        item['author'] = {
            "name": data_json['ep_show_name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if data_json.get('categories'):
        item['tags'] += [x['title'] for x in data_json['categories']]
    if data_json.get('keywords'):
        item['tags'] += data_json['keywords'].split(',')
    if len(item['tags']) == 0:
        del item['tags']

    item['image'] = data_json['thumbnail_file']

    if data_json.get('summary'):
        item['summary'] = data_json['summary']
    elif data_json.get('seo_desc'):
        item['summary'] = data_json['seo_desc']

    if 'shorts' in paths:
        item['_video'] = data_json['mp4_video_url']
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['image'], item['title'], use_videojs=True)
        return item
    elif data_json['type'] == 'video':
        if data_json.get('video_url') and '.mp4' in data_json['video_url']:
            item['_video'] = data_json['video_url']
            item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['image'], item['title'], use_videojs=True)
        else:
            logger.warning('unhandled video in ' + item['url'])
        if 'embed' not in args and 'summary' in item:
            item['content_html'] += '<p>' + item['summary'] + '</p>'
        return item
    elif 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    def format_content(content_html):
        soup = BeautifulSoup(content_html, 'html.parser')
        for el in soup.find_all('blockquote'):
            el['style'] = 'border-left:3px solid light-dark(#ccc, #333); margin:1.5em 10px; padding:0.5em 10px;'

        for el in soup.select('p:has(> iframe)'):
            new_html = utils.add_embed(el.iframe['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in soup.select('p:has(> a[href*="sportsgrid.com/newsletter/"])'):
            el.decompose()

        for el in soup.select('p:has(> a[href*="sportsgrid.com/betting/sportsbook-promos/"])'):
            el.decompose()

        for el in soup.select('p:has(> span > a[href*="sportsgrid.com/betting/sportsbook-promos/"])'):
            el.decompose()

        return str(soup)

    item['content_html'] = ''
    if data_json.get('post_content'):
        item['content_html'] += format_content(data_json['post_content'])

    if data_json.get('slider_data'):
        item['content_html'] += '<h2><a href="{}/gallery?url={}" target="_blank">View slideshow</a></h2>'.format(config.server, quote_plus(item['url']))
        item['_gallery'] = []
        for slider in data_json['slider_data']:
            if 'Download' in slider['title']:
                continue
            img_src = slider['contentUrl']
            captions = []
            if slider.get('caption'):
                captions.append(slider['caption'])
            if slider.get('credit'):
                captions.append(slider['credit'])
            caption = ' | '.join(captions)
            desc = ''
            if slider.get('title'):
                desc += '<h3>' + slider['title'] + '</h3>'
            if slider.get('description'):
                desc += format_content(slider['description'])
            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": img_src, "desc": desc})
            item['content_html'] += utils.add_image(img_src, caption, desc=desc) + '<div>&nbsp;</div>'

    return item


def get_feed(url, args, site_json, save_debug=False):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIxIiwianRpIjoiMTdkMzE0MzFmYTU3MjVhY2YzMDg0NzIxMjVkMzg2OGY4MmQ5YTUwMWVjZDM1YmNiZGQwYzAxNzM0ZGI0ZTFhODU3OGJmNzc5NzEyMDcyODkiLCJpYXQiOjE2ODkxNjk1NzAuMjE2NTI0LCJuYmYiOjE2ODkxNjk1NzAuMjE2NTI2LCJleHAiOjE3MjA3OTE5NzAuMjEzODg0LCJzdWIiOiIxNjEyIiwic2NvcGVzIjpbXX0.FJYBCYgShPgAeOsRbpbrEMTMV13Mp7SDlXJV8mnngaW1iesHYedMv07H6w4qpzJ6wbYPVRun9qjD8RqNYlc7dHa7vFLT1bUNHSWdfRepxV20-jzmC0hC1IKLMwG94QgvT-T6-8vH6zEWAFOcnX6UuffzoKIJ7H-Pz859YeECDCD1fjdI1dS7MB5-1mqTohmBf-JrCm5wRL2yd5IbDu_BR90v_VZ6CoxEVBzAj0_BQnmPtjalf6OPsjc2eJ2iztYf06WyiX2gDpDhQXhUVqku9q7zVQNme0043VHIZSVMDsZ-G3RY0b2CkREINAPeW-PKzUk80j2wf5TWiBkgMDVYyuy5BId_UavvYnG7oNseeMcmcanzkeIkb1bqkpzok35-K9-zbZ4q6cyLWe8Xhkx8a0epUJ7KEy3ROwaMRLr6MYbadioj2JPgETC7NNia5vhQSz1iTkygBfvQiPaNNVMV4-MIbiGvgfgWkiud3tA7DLrSm8DpuA51--vx1EzQw35Gs3KDfJr9M-Nu69iOybeT44__OnRu1QjntgmlgJKN4b30qq4wYB8hyzusprxAlqFN4tYkOhQQCtEP5fu2dGqpWFZiZj9RFuKb2yvaKaBl70L0Vw-BMj8PLevsHTHRXVbPNANWY0NrL2O1QlfHHDn-AUE-LsFlue-yudX5_u8KhoE",
        "content-type": "application/json",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Not A(Brand\";v=\"8\", \"Chromium\";v=\"132\", \"Microsoft Edge\";v=\"132\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    feed_title = ''
    api_url = 'https://web.sportsgrid.com/api/web/v1/getLoadMoreData'
    if len(paths) == 0:
        api_data = {
            "published_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "slug": "",
            "tag_id": ""
        }
        feed_title = 'Latest Articles and Videos | SportsGrid'
    elif len(paths) == 1:
        # Sport/league
        api_data = {
            "published_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "slug": paths[0],
            "tag_id": ""
        }
        feed_title = paths[0].uppercase() + ' News and Videos | SportsGrid'
    elif len(paths) > 1:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/next.json')
        if 'players' in paths:
            api_json = {
                "data": {
                    "data": []
                }
            }
            api_json['data']['data'] += next_data['pageProps']['ssr_data']['mobile_headlines']['data']
            api_json['data']['data'] += next_data['pageProps']['ssr_data']['latest_videos']['data']
            api_data = None
            feed_title = next_data['pageProps']['ssr_data']['title'] + ' | SportsGrid'
        elif next_data['pageProps']['ssr_data'].get('load_more_filter'):
            data_filter = next_data['pageProps']['ssr_data']['load_more_filter']
            feed_title = next_data['pageProps']['ssr_data']['title'] + ' | SportsGrid'
            api_data = {
                "published_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "slug": "no_sport",
                "filter": json.dumps(data_filter, separators=(',', ':'))
            }
        else:
            api_data = None

    if api_data:
        api_json = utils.post_url(api_url, json_data=api_data, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for data in api_json['data']['data']:
        data_url = 'https://www.sportsgrid.com{}'.format(data['web_url'])
        if save_debug:
            logger.debug('getting content for ' + data_url)
        if data['type'] == 'video':
            item = get_content(data_url, args, site_json, save_debug, data)
        else:
            item = get_content(data_url, args, site_json, save_debug, None)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
