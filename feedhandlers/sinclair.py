import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # Content sites https://sbgi.net/tv-stations/
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    base_url = split_url.scheme + '://' + split_url.netloc
    api_url = base_url + '/api/rest/facade/story/' + paths[-1]
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    article_json = api_json['data'][0]

    item = {}
    item['id'] = article_json['uuid']
    item['url'] = '{}{}{}'.format(base_url, article_json['primaryTarget']['sections'][0]['navigationPath'], article_json['canonicalUrl'])
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['publishedDateISO8601']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": article_json['byLine']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if article_json.get('tags'):
        item['tags'] = []
        for it in article_json['tags']:
            item['tags'].append(it['name'])

    if article_json.get('teaserImage'):
        item['image'] = '{}{}'.format(base_url, article_json['teaserImage']['image']['originalUrl'])
    elif article_json.get('heroImage'):
        item['image'] = '{}{}'.format(base_url, article_json['heroImage']['image']['originalUrl'])
    elif article_json.get('videos'):
        item['image'] = article_json['videos'][0]['thumbUrl']

    if article_json.get('summary'):
        item['summary'] = article_json['summary']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    if article_json.get('dateLine'):
        item['content_html'] += '{p}' + article_json['dateLine'] + ' &mdash; '
        if article_json.get('richText'):
            item['content_html'] += re.sub(r'^\{p\}', '', article_json['richText'].replace('{&nbsp;}', '&nbsp;'))
    elif article_json.get('richText'):
        item['content_html'] += article_json['richText'].replace('{&nbsp;}', '&nbsp;')

    item['content_html'] = re.sub(r'\{h2\}(MORE|ALSO)(\s|\{?&nbsp;\}?)?(:|\|)(\s|\{?&nbsp;\}?)\{a .*?\{/h2\}', '', item['content_html'])
    item['content_html'] = re.sub(r'\{p\}\{strong\}.*?(ALSO|ALSO READ|MORE|RELATED)(\s|\{?&nbsp;\}?)?(:|\|)(\s|\{?&nbsp;\}?)\{a .*?\{/a\}\{/strong\}\{/p\}', '', item['content_html'])
    item['content_html'] = re.sub(r'\{ul\}\{li\}\{em\}\{strong\}.*?(MORE|ALSO)(\s|\{?&nbsp;\}?)?(:|\|)(\s|\{?&nbsp;\}?)\{a .*?\{/li\}\{/ul\}', '', item['content_html'])
    item['content_html'] = re.sub(r'{(/?(a|blockquote|em|h\d|li|p|strong|ul))}', r'<\1>', item['content_html'])
    item['content_html'] = item['content_html'].replace('<blockquote>', '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;">')
    item['content_html'] = re.sub(r'{(br|hr)}', r'<\1/>', item['content_html'])
    item['content_html'] = re.sub(r'{a href="([^"]+)"[^}]*}', r'<a href="\1">', item['content_html'])

    def sub_embeds(matchobj):
        nonlocal article_json
        nonlocal base_url
        m = re.search(r'data-embed-type="([^"]+)"', matchobj.group(0))
        if m:
            embed_type = m.group(1)
            if embed_type == 'image':
                m = re.search(r'data-externalid="([^"]+)"', matchobj.group(0))
                # print(m.group(0))
                if m:
                    image = next((it for it in article_json['images'] if it.get('externalId') == m.group(1)), None)
                    if image:
                        img_src = base_url + image['originalUrl']
                        if image.get('caption'):
                            caption = re.sub(r'\{/?(p|&nbsp;)\}', '', image['caption'])
                        else:
                            caption = ''
                        return utils.add_image(img_src, caption)
            elif embed_type == 'video':
                m = re.search(r'data-externalid="([^"]+)"', matchobj.group(0))
                if m:
                    video = next((it for it in article_json['videos'] if it.get('externalId') == m.group(1)), None)
                    if video:
                        if video['thumbUrl'].startswith('/'):
                            img_src = base_url + video['thumbUrl']
                        else:
                            img_src = video['thumbUrl']
                        m = re.search(r'data-caption="([^"]+)"', matchobj.group(0))
                        if m:
                            caption = unquote_plus(m.group(1))
                        else:
                            caption = video['title']
                        return utils.add_video(video['mp4Url'], 'video/mp4', img_src, caption)
            elif embed_type == 'youtube':
                m = re.search(r'data-embed-file="([^"]+)"', matchobj.group(0))
                if m:
                    return utils.add_embed(m.group(1))
            elif embed_type == 'twitter':
                m = re.search(r'data-embed-file="([^"]+)"', matchobj.group(0))
                if m:
                    return utils.add_embed(utils.get_twitter_url(m.group(1)))
            elif embed_type == 'instagram':
                m = re.search(r'data-embed-file="([^"]+)"', matchobj.group(0))
                if m:
                    soup = BeautifulSoup(unquote_plus(m.group(1)), 'html.parser')
                    el = soup.find('blockquote')
                    if el:
                        return utils.add_embed(el['data-instgrm-permalink'])
            elif embed_type == 'facebook':
                m = re.search(r'data-embed-file="([^"]+)"', matchobj.group(0))
                if m:
                    soup = BeautifulSoup(unquote_plus(m.group(1)), 'html.parser')
                    el = soup.find('iframe')
                    if el:
                        return utils.add_embed(el['src'])
            elif embed_type == 'code':
                m = re.search(r'data-embed-file="([^"]+)"', matchobj.group(0))
                if m:
                    soup = BeautifulSoup(unquote_plus(m.group(1)), 'html.parser')
                    utils.write_file(str(soup), './debug/code.html')
                    el = soup.find('iframe')
                    if el:
                        return utils.add_embed(el['src'])
                    el = soup.find('blockquote', class_='tiktok-embed')
                    if el:
                        return utils.add_embed(el['cite'])
                    el = soup.find('blockquote', class_='instagram-media')
                    if el:
                        return utils.add_embed(el['data-instgrm-permalink'])
                    el = soup.find(class_='tagboard-embed')
                    if el:
                        return utils.add_embed('https://embed.tagboard.com/{}'.format(el['tgb-embed-id']), {"referer": base_url})
                    el = soup.select('a:has(> div:is(.subscribeShortcodeContainer, .donateContainer))')
                    if el:
                        # https://cbs2iowa.com/news/local/iowa-educators-breathe-sigh-of-relief-as-court-blocks-controversial-book-ban-law
                        for it in el:
                            it.decompose()
                        for it in soup.find_all(['script', 'style']):
                            it.decompose()
                        if m.group(1).startswith('<div>'):
                            return soup.div.decode_contents()
                        else:
                            return str(soup)
            logger.warning('unhandled sd-embed type ' + embed_type)
        return matchobj.group(0)

    item['content_html'] = re.sub(r'{sd-embed [^}]+}(<="" sd-embed="">)?{/sd-embed}', sub_embeds, item['content_html'])

    lede_html = ''
    if article_json.get('videos'):
        lede_html = utils.add_video(article_json['videos'][0]['mp4Url'], 'video/mp4', article_json['videos'][0]['thumbUrl'], article_json['videos'][0]['title'], use_videojs=True)
    elif article_json.get('heroImage'):
        img_src = base_url + article_json['heroImage']['image']['originalUrl']
        if article_json['heroImage']['image'].get('caption'):
            caption = re.sub(r'\{/?(p|&nbsp;)\}', '', article_json['heroImage']['image']['caption'])
        else:
            caption = ''
        lede_html = utils.add_image(img_src, caption)

    n = len(article_json['images']) + len(article_json['videos'])
    if n > 1:
        item['_gallery'] = []
        for i in range(1, n + 1):
            image = next((it for it in article_json['images'] if it['orderNumber'] == i), None)
            if image:
                img_src = base_url + image['originalUrl']
                thumb = img_src.replace('/resources/media/', '/resources/media2/original/full/640/center/80/')
                if image.get('caption'):
                    caption = re.sub(r'\{/?(p|&nbsp;)\}', '', image['caption'])
                else:
                    caption = ''
                item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb})
            else:
                video = next((it for it in article_json['videos'] if it['orderNumber'] == i), None)
                if video:
                    if video['thumbUrl'].startswith('/'):
                        img_src = base_url + video['thumbUrl']
                    else:
                        img_src = video['thumbUrl']
                    if video.get('title'):
                        caption = video['title']
                    else:
                        caption = ''
                    item['_gallery'].append({"src": video['mp4Url'], "caption": caption, "thumb": img_src, "video_type": 'video/mp4'})
        lede_html = utils.add_gallery(item['_gallery'], show_thumbnails=True)

    item['content_html'] = lede_html + item['content_html']
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)
    api_url = '{}/api/rest/audience/more?section={}{}&limit=10'.format(base_url, split_url.netloc, split_url.path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    feed = utils.init_jsonfeed(args)
    for article in api_json['data']:
        article_url = base_url + article['url']
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
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed

