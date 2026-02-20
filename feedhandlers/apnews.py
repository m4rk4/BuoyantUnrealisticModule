import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # Need an api key to use the official developer api
    # https://developer.ap.org/ap-media-api/agent/Feeds_and_Linked_Content.htm
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    page_soup = BeautifulSoup(page_html, 'lxml')
    ld_json = []
    for el in page_soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld = json.loads(el.string)
        if isinstance(ld, list):
            ld_json += ld
        elif isinstance(ld, dict):
            ld_json.append(ld)

    if len(ld_json) == 0:
        logger.warning('unable to find ld+json in ' + url)
        return None
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    ld_article = next((it for it in ld_json if it.get('@type') == 'NewsArticle'), None)
    if not ld_article:
        logger.warning('unable to find ld+json NewsArticle in ' + url)
        return None

    item = {}
    item['id'] = ld_article['url'].split('-')[-1]
    item['url'] = ld_article['url']
    item['title'] = ld_article['headline']

    dt = datetime.fromisoformat(ld_article['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_article.get('dateModified'):
        dt = datetime.fromisoformat(ld_article['dateModified'])
        item['date_modified'] = dt.isoformat()

    if ld_article.get('author'):
        item['authors'] = [{"name": x["name"]} for x in ld_article['author']]
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
    elif ld_article.get('publisher'):
        item['author'] = {
            "name": ld_article['publisher']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = ld_article['articleSection'].copy()
    if ld_article.get('keywords'):
        item['tags'] += ld_article['keywords'].copy()

    if ld_article.get('description'):
        item['summary'] = ld_article['description']

    if ld_article.get('mainEntity') and ld_article['mainEntity']['@type'] == 'VideoObject':
        item['image'] = ld_article['mainEntity']['thumbnailUrl']
        el = page_soup.find('meta', attrs={"property": "og:video"})
        if el:
            src = el['content']
            el = page_soup.find('meta', attrs={"property": "og:video:type"})
            item['content_html'] = utils.add_video(src, el['content'], item['image'], item['title'])
            if 'embed' not in args and 'summary' in item:
                item['content_html'] += '<p>' + item['summary'] + '</p>'
            return item
    else:
        item['image'] = ld_article['thumbnailUrl']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    el = page_soup.find('div', class_='Page-lead')
    if el:
        if el.find('bsp-carousel'):
            item['_gallery'] = []
            for slide in el.select('bsp-carousel div.Carousel-slide'):
                media = slide.find(class_='CarouselSlide-media')
                if 'imageSlide' in media['class']:
                    images = []
                    for it in slide.find_all('source', attrs={"type": "image/webp"}):
                        if it.get('data-flickity-lazyload-srcset'):
                            srcset = it['data-flickity-lazyload-srcset']
                        elif it.get('srcset'):
                            srcset = it['srcset']
                        for m in re.findall(r'(https[^\s]+)\s(\d)x', srcset):
                            images.append({"src": m[0], "width":int(it['width'] * int(m[1]))})
                    src = utils.closest_dict(images, 'width', 2000)['src']
                    thumb = utils.closest_dict(images, 'width', 640)['src']
                    it = slide.select('.CarouselSlide-infoDescription > p')
                    if it:
                        caption = it[0].decode_contents().strip()
                    else:
                        caption = ''
                    item['_gallery'].append({"src": src, "caption": caption, "thumb": thumb})
                elif 'videoSlide' in media['class']:
                    player = media.find(['bsp-jw-player'])
                    if player:
                        video_data = json.loads(player['data-video-datalayer'])
                        src = video_data['proximic_video_source_url']
                        caption = video_data['headline']
                        thumb = 'https://cdn.jwplayer.com/v2/media/' + player['data-media-id'] + '/poster.jpg?width=1280'
                        item['_gallery'].append({"src": src, "caption": caption, "thumb": thumb, "video_type": "video/mp4"})
                else:
                    logger.warning('unhandled CarouselSlide-media class ' + media['class'])
            # gallery_url = config.server + '/gallery?url=' + quote_plus(item['url'])
            item['content_html'] += utils.add_gallery(item['_gallery'], show_thumbnails=True)
        elif el.find('bsp-figure'):
            images = []
            for it in el.find_all('source', attrs={"type": "image/webp"}):
                if it.get('data-flickity-lazyload-srcset'):
                    srcset = it['data-flickity-lazyload-srcset']
                elif it.get('srcset'):
                    srcset = it['srcset']
                for m in re.findall(r'(https[^\s]+)\s(\d)x', srcset):
                    images.append({"src": m[0], "width":int(it['width'] * int(m[1]))})
            src = utils.closest_dict(images, 'width', 1200)['src']
            el = el.select('.Figure-caption > p')
            if el:
                caption = el[0].decode_contents().strip()
            else:
                caption = ''
            item['content_html'] += utils.add_image(src, caption)

    ld_review = next((it for it in ld_json if it.get('review')), None)
    if ld_review and ld_review['review'].get('reviewRating'):
        item['content_html'] += utils.add_stars(float(ld_review['review']['reviewRating']['ratingValue']), int(ld_review['review']['reviewRating']['bestRating']), show_rating=True)

    story_body = page_soup.select('main.Page-main > bsp-story-page > div.Page-storyBody > div.RichTextStoryBody')
    if story_body:
        body = story_body[0]
        for el in body.find_all(class_=['Advertisement', 'SovrnAd', 'optimizelyHubpeekClass']):
            el.decompose()

        for el in body.find_all(class_='Enhancement'):
            new_html = ''
            if el.find('bsp-list-loadmore'):
                el.decompose()
                continue
            elif el.find(class_='ImageEnhancement'):
                if el.find('bsp-figure'):
                    images = []
                    for it in el.find_all('source', attrs={"type": "image/webp"}):
                        if it.get('data-flickity-lazyload-srcset'):
                            srcset = it['data-flickity-lazyload-srcset']
                        elif it.get('srcset'):
                            srcset = it['srcset']
                        for m in re.findall(r'(https[^\s]+)\s(\d)x', srcset):
                            images.append({"src": m[0], "width":int(it['width'] * int(m[1]))})
                    src = utils.closest_dict(images, 'width', 1200)['src']
                    it = el.select('.Figure-caption > p')
                    if it:
                        caption = it[0].decode_contents().strip()
                    else:
                        caption = ''
                    new_html = utils.add_image(src, caption, link=src)
            elif el.find(class_='ImageTwoUpEnhancement'):
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for media in el.find_all('bsp-figure'):
                    srcset = re.split(r'\s\dx,?', media.img['srcset'])
                    src = srcset[1]
                    it = el.find('figcaption', class_='Figure-caption')
                    if it:
                        if it.p:
                            caption = it.p.decode_contents().strip()
                        else:
                            caption = it.decode_contents().strip()
                    else:
                        caption = ''
                    new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(src, caption) + '</div>'
                new_html += '</div>'
            elif el.find(class_='VideoEnhancement'):
                player = el.find('bsp-jw-player')
                new_html = utils.add_embed('https://cdn.jwplayer.com/v2/media/' + player['data-media-id'])
            elif el.find(class_='PullQuote'):
                it = el.find(class_='PullQuote-content-attribution')
                if it:
                    caption = it.decode_contents()
                else:
                    caption = ''
                new_html = utils.add_pullquote(el.blockquote.decode_contents(), caption)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled Enhancement in ' + item['url'])

        for el in body.find_all(class_='AudioEnhancement'):
            it = el.find('source')
            if it:
                new_html = utils.format_audio_track({"src": it['src'], "mime_type": it['type'], "title": el['data-gtm-region'], "image": "https://cdn.cookielaw.org/logos/9efcd77d-fbf7-40b0-a4b6-8fe108d3d374/019055ad-d9c4-7310-b8fc-2fb952ee33e6/d7d8495e-b2ba-4e73-ae16-9d4001a20788/AP_Logo.png"}, full_width=False)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled  in AudioEnhancement ' + item['url'])

        for el in body.find_all(class_='HTMLModuleEnhancement'):
            if el.find_all(class_=['taboola_readmore', 'ap-embed-whatsapp']):
                el.decompose()
            elif el.find('iframe', id=re.compile(r'ap-chart-')):
                new_html = utils.add_embed(el.iframe['src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            elif el.find('iframe', class_='ap-embed', attrs={"src": re.compile(r'interactives\.ap\.org')}):
                it = el.find(class_='embed-caption')
                if it and it.get_text(strip=True):
                    caption = it.decode_contents()
                else:
                    caption = ''
                new_html = utils.add_image(config.server + '/screenshot?url=' + quote_plus(el.iframe['src']) + '&cropbbox=1', caption, link=el.iframe['src'], overlay=config.chart_button_overlay)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            elif el.find(class_='ap-review-embed'):
                it = el.find(class_='ap-review-embed')
                new_html = '<div style="background-color:light-dark(#ccc,#333); border-radius:10px; padding:1em; max-width:540px; margin:1em auto;">'
                new_html += '<div style="text-align:center;"><img src="' + it['data-cover'] + '" style="width:180px;"></div>'
                new_html += '<div style="text-align:center; margin:4px; font-size:larger; font-weight:bold;">' + it['data-album'] + '</div>'
                new_html += '<div style="text-align:center; font-weight:bold;">' + it['data-artist'] + '</div>'
                new_html += utils.add_stars(float(it['data-rating']), star_size='2em', show_rating=True)
                if it.get('data-repeat'):
                    new_html += '<div style="margin:4px 1em;"><b>On repeat:</b> ' + it['data-repeat'] + '</div>'
                if it.get('data-skip'):
                    new_html += '<div style="margin:4px 1em;"><b>Skip it:</b> ' + it['data-skip'] + '</div>'
                if it.get('data-fans'):
                    new_html += '<div style="margin:4px 1em;"><b>For fans of:</b> ' + it['data-fans'] + '</div>'
                new_html += '</div>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled HTMLModuleEnhancement in ' + item['url'])

        item['content_html'] += body.decode_contents()

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://apnews.com/hub/ap-top-news
    # https://github.com/DIYgod/RSSHub/blob/master/lib/routes/apnews/mobile-api.ts
    split_url = urlsplit(url)
    api_url = 'https://apnews.com/graphql/delivery/ap/v1'
    query = {
        "operationName": "ContentPageQuery",
        "variables": {
            "path": split_url.path
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "3bc305abbf62e9e632403a74cc86dc1cba51156d2313f09b3779efec51fc3acb"
            }
        }
    }
    api_json = utils.post_url(api_url, json_data=query)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    page_urls = []
    def iter_module(module):
        nonlocal page_urls
        if module['__typename'] == 'ColumnContainer':
            for it in module['columns']:
                iter_module(it)
        elif module['__typename'] == 'PageListModule':
            for it in module['items']:
                iter_module(it)
        elif module['__typename'] == 'PagePromo':
            page_urls.append(module['url'])
        elif module['__typename'] == 'VideoPlaylistModule':
            for it in module['playlist']:
                iter_module(it)
        elif module['__typename'] == 'VideoPlaylistItem':
            page_urls.append(module['url'])
        elif module['__typename'] == 'GoogleDfPAdModule' or module['__typename'] == 'NativoAd' or module['__typename'] == 'TaboolaRecommendationModule':
            pass
        else:
            logger.warning('unhandled page module ' + module['__typename'])
    for module in api_json['data']['Screen']['main']:
        iter_module(module)

    n = 0
    items = []
    for page_url in page_urls:
        if save_debug:
            logger.debug('getting content for ' + page_url)
        item = get_content(page_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args and n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['title'] = api_json['data']['Screen']['title']
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
