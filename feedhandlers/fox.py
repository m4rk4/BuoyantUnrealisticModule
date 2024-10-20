import math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    if re.search(r'static\.fox(business|news|sports)\.com', split_url.netloc):
        w, h = utils.get_image_size(img_src)
        if not w or not h:
            return img_src
        height = math.floor(h * width / w)
        paths.insert(-1, str(width))
        paths.insert(-1, str(height))
        img_src = 'https://a57.foxnews.com/{}/{}?ve=1&tl=1'.format(split_url.netloc, '/'.join(paths))
    elif split_url == 'a57.foxnews.com':
        w = int(paths[-3])
        h = int(paths[-2])
        height = math.floor(h * width / w)
        paths[-3] = str(width)
        paths[-2] = str(height)
        img_src = 'https://a57.foxnews.com/{}?ve=1&tl=1'.format('/'.join(paths))
    return img_src


def add_image(image, width=1000):
    img_src = resize_image(image['url'])
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('copyright'):
        captions.append(image['copyright'])
    return utils.add_image(img_src, ' | '.join(captions))


def add_video(video):
    # https://api.foxbusiness.com/v3/video-player/6306532261112
    video_type = video.get('video_type')
    if not video_type:
        video_type = video.get('external_source')
    if re.search(r'brightcove', video_type, flags=re.I):
        title = re.sub(r'\sI\s', ' | ', video['title'])
        caption = '<strong>{}</strong><br/>{}'.format(title, video['description'])
        return utils.add_video(video['playback_url'], 'application/x-mpegURL', video['thumbnail'], caption)
    elif re.search(r'delta', video_type, flags=re.I):
        video_json = utils.get_url_json(video['playback_url'])
        if video_json:
            utils.write_file(video_json, './debug/video.json')
            title = re.sub(r'\sI\s', ' | ', video_json['name'])
            caption = '<strong>{}</strong><br/>{}'.format(title, video_json['description'])
            return utils.add_video(video_json['url'], 'application/x-mpegURL', video_json['image'], caption)
    else:
        logger.warning('unhandled video type ' + video['video_type'])
    return ''


def get_video_content(url, args, site_json, save_debug=False):
    m = re.search(r'/v/(\d+)', url)
    if not m:
        logger.warning('unhandled video url ' + url)
        return None
    api_url = 'https://api.foxnews.com/v3/video-player/' + m.group(1)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    video_json = api_json['channel']['item']
    if save_debug:
        utils.write_file(video_json, './debug/video.json')
    item = {}
    item['id'] = video_json['guid']
    item['url'] = video_json['link']
    item['title'] = video_json['title']
    dt = datetime.fromisoformat(video_json['dc-date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if video_json.get('dc-creator'):
        item['author'] = {
            "name": video_json['dc-creator']
        }
    elif video_json.get('dc-contributor'):
        item['author'] = {
            "name": video_json['dc-contributor']
        }
    elif video_json.get('dc-source'):
        item['author'] = {
            "name": video_json['dc-source']
        }
    elif video_json.get('publisher'):
        item['author'] = {
            "name": video_json['publisher']
        }
    if 'author' in item:
        item['authors'] = []
        item['authors'].append(item['author'])
    item['tags'] = []
    for cat in video_json['category']:
        for it in cat.split('|'):
            tag = it.replace('_', ' ')
            if tag not in item['tags'] and 'ad supported' not in tag and tag != 'personality':
                item['tags'].append(tag)
    item['image'] = video_json['media-group']['media-thumbnail']['@attributes']['url']
    item['summary'] = video_json['description']
    video = None
    for video_type in ['video/mp4', 'application/x-mpegURL']:
        for media in video_json['media-group']['media-content']:
            if media['@attributes']['type'] == video_type:
                video = media['@attributes']
                break
        if video:
            break
    item['content_html'] = utils.add_video(video['url'], video['type'], item['image'], item['summary'])
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.netloc.startswith('video.'):
        return get_video_content(url, args, site_json, save_debug)
    elif 'foxbusiness' in split_url.netloc:
        canonical_url = 'foxbusiness.com' + split_url.path
        api_url = 'https://api.foxbusiness.com/spark/articles?searchBy=urls&type=&values=' + quote_plus(canonical_url)
    elif 'foxnews' in split_url.netloc:
        canonical_url = 'foxnews.com' + split_url.path
        api_url = 'https://api.foxnews.com/spark/articles?searchBy=urls&type=&values=' + quote_plus(canonical_url)
    elif 'foxsports' in split_url.netloc:
        canonical_url = 'foxsports.com' + split_url.path
        if '/watch/' in split_url.path:
            api_url = 'https://prod-api.foxsports.com/fs/videos?searchBy=urls&values=' + quote_plus(canonical_url)
        else:
            api_url = 'https://prod-api.foxsports.com/fs/articles?searchBy=urls&values=' + quote_plus(canonical_url)
    else:
        logger.warning('unhandled url ' + url)
        return None

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    article_json = None
    for result in api_json['data']['results']:
        if result['canonical_url'] == canonical_url:
            article_json = result
            break

    if not article_json:
        if save_debug:
            utils.write_file(api_json, './debug/debug.json')
        logger.warning('unable to find article content for ' + url)
        return None

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://www.' + article_json['canonical_url']
    item['title'] = re.sub(r'\sI\s', ' | ', article_json['title'])

    date = ''
    if article_json.get('publication_date'):
        date = article_json['publication_date']
    elif article_json.get('original_import_date'):
        date = article_json['original_import_date']
    if date:
        if date.endswith('Z'):
            date = date.replace('Z', '+00:00')
        dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    date = ''
    if article_json.get('last_modified_date'):
        date = article_json['last_modified_date']
    elif article_json.get('last_published_date'):
        date = article_json['last_published_date']
    if date:
        if date.endswith('Z'):
            date = date.replace('Z', '+00:00')
        dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = []
    if article_json.get('fn__contributors'):
        for it in article_json['fn__contributors']:
            item['authors'].append({"name": it['full_name']})
    elif article_json.get('spark_persons'):
        for it in article_json['spark_persons']:
            item['authors'].append({"name": it['full_name']})
    if article_json.get('fn__additional_authors'):
        for it in article_json['fn__additional_authors']:
            item['authors'].append({"name": it})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('tags'):
        for tag in article_json['tags']:
            item['tags'].append(tag['title'])
    if not item.get('tags'):
        del item['tags']

    if article_json.get('thumbnail'):
        if article_json['thumbnail']['content_type'] == 'image':
            if article_json['thumbnail'].get('content'):
                item['image'] = article_json['thumbnail']['content']['url']
            else:
                item['image'] = article_json['thumbnail']['url']
        elif article_json['thumbnail']['content_type'] == 'video':
            item['image'] = article_json['thumbnail']['content']['thumbnail']
        else:
            logger.debug('unhandled thumbnail type {} in {}'.format( article_json['thumbnail']['content_type'], item['url']))

    if article_json.get('dek'):
        item['summary'] = article_json['dek']
    elif article_json.get('standfirst'):
        item['summary'] = article_json['standfirst']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    if article_json.get('standfirst'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['standfirst'])

    if article_json['component_type'] == 'video':
        item['content_html'] += add_video(article_json)
        return item

    if not re.search(r'image|video|brightcove', article_json['components'][0]['content_type']):
        if article_json['thumbnail']['content_type'] == 'image':
            item['content_html'] += add_image(article_json['thumbnail']['content'])
        elif article_json['thumbnail']['content_type'] == 'video':
            item['content_html'] += add_video(article_json['thumbnail']['content'])

    for component in article_json['components']:
        if component['content_type'] == 'text':
            if component['content']['text'].startswith('<p><a href='):
                if re.search(r'ApArticleLink', component['content']['text']) or re.search(r'<strong>(<u>)?[A-Z0-9\W]+(</u>)?</strong>', component['content']['text']):
                    # Usually a links to related content or signup
                    continue
            item['content_html'] += component['content']['text']
        elif component['content_type'] == 'heading':
            item['content_html'] += '<h{0}>{1}</h{0}>'.format(component['content']['rank'], component['content']['text'])
        elif component['content_type'] == 'pull_quote':
            item['content_html'] += utils.add_pullquote(component['content']['text'], component['content']['credit'])
        elif component['content_type'] == 'image':
            item['content_html'] += add_image(component['content'])
        elif component['content_type'] == 'image_gallery':
            for image in component['content']['images']:
                item['content_html'] += add_image(image) + '<br/>'
        elif component['content_type'] == 'youtube_video' or component['content_type'] == 'twitter_tweet':
            item['content_html'] += utils.add_embed(component['content']['url'])
        elif re.search(r'brightcove|delta_video', component['content_type']):
            item['content_html'] += add_video(component['content'])
        elif component['content_type'] == 'list':
            if component['content']['ordered'] == True:
                tag = 'ol'
            else:
                tag = 'ul'
            item['content_html'] += '<{}>'.format(tag)
            for it in component['content']['items']:
                item['content_html'] += '<li>{}</li>'.format(it['content']['title'])
            item['content_html'] += '</{}>'.format(tag)
        elif component['content_type'] == 'freeform':
            if component['content']['text'] == '<hr>':
                item['content_html'] += component['content']['text']
            elif re.search(r'widgets\.foxsuper6\.com', component['content']['text']):
                pass
            elif re.search(r'<iframe', component['content']['text']):
                soup = BeautifulSoup(component['content']['text'], 'html.parser')
                item['content_html'] += utils.add_embed(soup.iframe['src'])
            else:
                logger.warning('unhandled freeform content in ' + item['url'])
        elif component['content_type'] == 'stock_table':
            stock_json = utils.get_url_json('https://api.foxbusiness.com/factset/stock-search?stockType=quoteInfo&identifiers=US:{}&isIndex=true'.format(component['content']['values']))
            if stock_json:
                item['content_html'] += '<table style="width:100%; border:1px solid black; border-collapse:collapse;"><tr style="border:1px solid black; border-collapse:collapse;"><th>Ticker</th><th>Security</th><th>Last</th><th>Change</th><th>Change %</th></tr><tr><td style="text-align:center;"><a href="https://www.foxbusiness.com/quote?stockTicker={0}">{0}</a></td><td style="text-align:center;">{1}</td><td style="text-align:center;">{2}</td><td style="text-align:center;">{3}</td><td style="text-align:center;">{4}</td></tr></table>'.format(stock_json['data'][0]['symbol'], stock_json['data'][0]['companyName'], stock_json['data'][0]['last'], stock_json['data'][0]['change'], stock_json['data'][0]['changePercent'])
            else:
                logger.warning('unable to get stock info for {} in {}'.format(component['content']['values'], item['url']))
        elif component['content_type'] == 'event_odds':
            if component['content']['odds_type'] == 'oddsSixPack':
                event_json = utils.get_url_json('https://api.foxsports.com/bifrost/v1/explore/entity/modules/event/{}?apikey=jE7yBJVRNAwdDesMgTzTXUUSx1It41Fq'.format(component['content']['event_uri']))
                if event_json:
                    utils.write_file(event_json, './debug/event.json')
                    item['content_html'] += '<table style="width:100%; border:1px solid black; border-collapse:collapse;"><caption style="caption-side:bottom; text-align:left;"><small>{}</small></caption><tr style="border:1px solid black; border-collapse:collapse;"><th style="text-align:left;">{}</th>'.format(event_json['odds']['insight'], event_json['odds']['odds']['title'])
                    for it in event_json['odds']['odds']['columnHeaders']:
                        item['content_html'] += '<th>{}</th>'.format(it)
                    item['content_html'] += '</tr>'
                    for row in event_json['odds']['odds']['rows']:
                        item['content_html'] += '<tr style="border:1px solid black; border-collapse:collapse;"><td><img src="{}" width="20" height="20" />&nbsp;{}</td>'.format(row['imageUrl'], row['fullText'])
                        for it in row['odds']:
                            item['content_html'] += '<td style="text-align:center;">{}</td>'.format(it)
                        item['content_html'] += '</tr>'
                    item['content_html'] += '</table>'

            else:
                logger.warning('unhandled event_odds type {} in {}'.format(component['content']['odds_type'], item['url']))
        elif component['content_type'] == 'credible' or component['content_type'] == 'favorite' or component['content_type'] == 'cultivate_forecast':
            pass
        else:
            logger.warning('unhandled content type {} in {}'.format(component['content_type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if re.search(r'\.xml|rss', args['url']):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    page_html = utils.get_url_html(args['url'])
    if not page_html:
        return None

    split_url = urlsplit(args['url'])
    n = 0
    items = []
    if split_url.netloc.startswith('video.'):
        m = re.search(r'site: "([^"]+)".*playlistId: "([^"]+)"', page_html, flags=re.S)
        if not m:
            logger.warning('unable to find playlistId for ' + args['url'])
            return None
        site = m.group(1)
        playlist_id = m.group(2)
        api_url = 'https://video.{}.com/v/feed/playlist/{}.json'.format(site, playlist_id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        for it in api_json['channel']['item']:
            url = 'https://video.{}.com/v/{}/?playlist_id={}'.format(site, it['media-content']['mvn-assetUUID'], playlist_id)
            if save_debug:
                logger.debug('getting content from ' + url)
            item = get_video_content(url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    elif 'foxsports' in split_url.netloc:
        if split_url.path.startswith('/shows/'):
            soup = BeautifulSoup(page_html, 'html.parser')
            for el in soup.find_all(attrs={"data-psu":True}):
                split_url = urlsplit(el['data-psu'])
                paths = list(filter(None, split_url.path.split('/')))
                url = 'https://www.foxsports.com/watch/' + paths[-1]
                if save_debug:
                    logger.debug('getting content from ' + url)
                item = get_content(url, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        items.append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break
        else:
            m = re.search(r'apiEndpointUrl:"([^"]+)"', page_html)
            if m:
                api_url = m.group(1).replace('\\u002F', '/')
                split_url = urlsplit(api_url)
                query = parse_qs(split_url.query)
                args_copy = args.copy()
                args_copy['url'] = 'https://api.foxsports.com/v2/content/optimized-rss?partnerKey=MB0Wehpmuj2lUhuRhQaafhBjAJqaPU244mlTDK1i&size=10&tags=' + query['uri'][0]
                return rss.get_feed(url, args_copy, site_json, save_debug, get_content)

    if not items:
        return None
    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed
