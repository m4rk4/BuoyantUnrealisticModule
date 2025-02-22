import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

from feedhandlers import jwplayer
import config, utils

import logging

logger = logging.getLogger(__name__)


def add_media(media):
    if media['type'] == 'Photo':
        size = utils.closest_value(media['imageRenderedSizes'], 1000)
        img_src = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
        size = max(media['imageRenderedSizes'])
        link = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
        media_html = utils.add_image(img_src, media.get('flattenedCaption'), link=link)
    elif media['type'] == 'Video' and media.get('jwVideoStatus'):
        media_html = utils.add_embed('https://cdn.jwplayer.com/v2/media/{}'.format(media['jwMediaId']))
    elif media['type'] == 'YouTube':
        media_html = utils.add_embed('https://www.youtube.com/watch?v={}'.format(media['externalId']))
    else:
        logger.warning('Unhandled media type {}'.format(media['type']))
        media_html = ''
    return media_html


def get_image_url(img_id, file_ext='.jpeg', img_width=600):
    return 'https://storage.googleapis.com/afs-prod/media/{}/{}{}'.format(img_id, img_width, file_ext)


def get_item(content_data, args, site_json, save_debug=False):
    item = {}
    item['id'] = content_data['id']
    item['url'] = content_data['localLinkUrl']
    item['title'] = content_data['headline']

    dt_pub = None
    if content_data.get('published'):
        dt_pub = datetime.fromisoformat(content_data['published']).replace(tzinfo=timezone.utc)
    dt_mod = None
    if content_data.get('updated'):
        dt_mod = datetime.fromisoformat(content_data['updated']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt_mod.isoformat()
    if not dt_pub and dt_mod:
        dt_pub = dt_mod
    if dt_pub:
        item['date_published'] = dt_pub.isoformat()
        item['_timestamp'] = dt_pub.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt_pub.strftime('%b'), dt_pub.day, dt_pub.year)

    if not utils.check_age(item, args):
        return None

    item['author'] = {}
    if content_data.get('bylines'):
        m = re.search(r'^By\s*(.*)', content_data['bylines'], flags=re.I)
        if m:
            item['author']['name'] = m.group(1).title().replace('And', 'and')
        else:
            item['author']['name'] = content_data['bylines'].title().replace('And', 'and')
    else:
        item['author']['name'] = 'AP News'
    item['authors'] = []
    item['authors'].append(item['author'])

    if content_data.get('tagObjs'):
        item['tags'] = []
        for tag in content_data['tagObjs']:
            item['tags'].append(tag['name'])

    if content_data.get('leadPhotoId'):
        item['image'] = get_image_url(content_data['leadPhotoId'])

    item['summary'] = content_data['flattenedFirstWords']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    story_soup = BeautifulSoup(content_data['storyHTML'], 'html.parser')

    for el in story_soup.find_all(class_=['ad-placeholder', 'hub-peek-embed']):
        el.decompose()

    for el in story_soup.find_all(class_='media-placeholder'):
        for media in content_data['media']:
            if media['id'] == el['id']:
                new_html = add_media(media)
                if new_html:
                    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                    el.decompose()
                    break

    for el in story_soup.find_all(class_='social-embed'):
        for embed in content_data['socialEmbeds']:
            if embed['id'] == el['id']:
                new_html = ''
                embed_soup = BeautifulSoup(embed['html'], 'html.parser')
                if embed_soup.iframe:
                    if embed_soup.iframe['src'].startswith('https://interactives.ap.org/embeds/'):
                        new_html = ''
                        src_html = utils.get_url_html(embed_soup.iframe['src'])
                        if src_html:
                            src_soup = BeautifulSoup(src_html, 'html.parser')
                            it = src_soup.find(id='header')
                            if it:
                                title = it.get_text()
                            else:
                                title = ''
                            it = src_soup.find('meta', attrs={"property": "og:image"})
                            if it:
                                new_html = utils.add_image(it['content'], title, link=embed_soup.iframe['src'])
                        if not new_html:
                            if embed_soup.iframe.get('title'):
                                title = embed_soup.iframe['title']
                            else:
                                title = embed_soup.iframe['src']
                            new_html = '<blockquote><b>Embedded content: <a href="{}">{}</a></b></blockquote>'.format(embed_soup.iframe['src'], title)
                    else:
                        new_html = utils.add_embed(embed_soup.iframe['src'])
                elif embed_soup.contents[0].name == 'img':
                    new_html = utils.add_image(embed_soup.img['src'])
                if new_html:
                    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                    el.decompose()
                break

    for el in story_soup.find_all(class_='related-story-embed'):
        for embed in content_data['relatedStoryEmbeds']:
            if embed['id'] == el['id']:
                new_html = '<h4>{}</h4><ul>'.format(embed['introText'])
                for li in embed['contentsList']:
                    title = ''
                    desc = ''
                    if li.get('contentId'):
                        li_json = utils.get_url_json('https://afs-prod.appspot.com/api/v2/content/' + li['contentId'])
                        if li_json:
                            title = li_json['headline']
                            desc = li_json['flattenedFirstWords']
                    else:
                        title, desc = utils.get_url_title_desc(li['url'])
                    new_html += '<li><b><a href="{}">{}</a></b><br />{}</li>'.format(li['url'], title, desc)
                new_html += '</ul>'
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()
                break

    for el in story_soup.find_all(class_='hub-link-embed'):
        for embed in content_data['richEmbeds']:
            if embed['id'] == el['id']:
                new_html = '<blockquote><b>{} &ndash; <a href="https://apnews.com/hub/{}">{}</a></b></blockquote'.format(embed['displayName'], embed['tag']['id'], embed['calloutText'])
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()
                break

    item['content_html'] = ''
    if content_data.get('leadVideoId'):
        media = next((it for it in content_data['media'] if it['id'] == content_data['leadVideoId']), None)
        if media:
            item['content_html'] = add_media(media)
    elif content_data.get('leadPhotoId'):
        media = next((it for it in content_data['media'] if it['id'] == content_data['leadPhotoId']), None)
        if media:
            item['content_html'] = add_media(media)
    elif item.get('image'):
        item['content_html'] = utils.add_image(item['image'])

    item['content_html'] += str(story_soup)

    gallery_images = []
    gallery_html = ''
    n = 0
    if content_data.get('media') and len(content_data['media']) > 1:
        for media in content_data['media']:
            m = re.search(media['id'], item['content_html'])
            if not m and media.get('externalId'):
                m = re.search(media['externalId'], item['content_html'])
            if not m:
                n += 1
            if media['type'] == 'Photo':
                size = utils.closest_value(media['imageRenderedSizes'], 600)
                thumb = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
                size = max(media['imageRenderedSizes'])
                src = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
                if media.get('flattenedCaption'):
                    caption = media['flattenedCaption']
                else:
                    caption = ''
                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=src) + '</div>'
                gallery_images.append({"src": src, "caption": caption, "thumb": thumb})
            elif media['type'] == 'Video' and media.get('jwVideoStatus'):
                media_item = utils.get_content('https://cdn.jwplayer.com/v2/media/' + media['jwMediaId'], {"embed": True}, False)
                if media_item:
                    size = max(media['imageRenderedSizes'])
                    thumb = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
                    src = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(media_item['_video']), quote_plus(media_item['_video_type']), quote_plus(thumb))
                else:
                    src = config.server + '/video?url=' + quote_plus('https://cdn.jwplayer.com/v2/media/' + media['jwMediaId'])
                size = utils.closest_value(media['imageRenderedSizes'], 600)
                thumb = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
                thumb = '{}/image?url={}&width=640&overlay=video'.format(config.server, quote_plus(thumb))
                if media.get('flattenedCaption'):
                    caption = media['flattenedCaption']
                else:
                    caption = ''
                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=src) + '</div>'
                if media_item and media_item['_video_type'] == 'video/mp4':
                    gallery_images.append({"src": media_item['_video'], "caption": caption, "thumb": thumb})
                elif media_item and '_video_mp4' in media_item:
                    gallery_images.append({"src": media_item['_video_mp4'], "caption": caption, "thumb": thumb})
                else:
                    gallery_images.append({"src": src, "caption": caption, "thumb": thumb})
            elif media['type'] == 'YouTube':
                size = utils.closest_value(media['imageRenderedSizes'], 600)
                thumb = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
                thumb = '{}/image?url={}&width=640&overlay=video'.format(config.server, quote_plus(thumb))
                src = config.server + '/video?url=' + quote_plus('https://www.youtube.com/watch?v=' + media['externalId'])
                if media.get('flattenedCaption'):
                    caption = media['flattenedCaption']
                else:
                    caption = ''
                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=src) + '</div>'
                gallery_images.append({"src": src + '&novideojs', "caption": caption, "thumb": thumb})
            else:
                logger.warning('unhandled media type {} in {}'.format(media['type'], item['url']))
    if n > 0:
        gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">' + gallery_html + '</div>'
        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
        item['content_html'] += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_content_api(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    m = re.search(r'([0-9a-f]+)\/?$', split_url.path)
    if not m:
        logger.warning('unable to parse article id from ' + url)
        return None

    article_json = utils.get_url_json('https://afs-prod.appspot.com/api/v2/content/' + m.group(1))
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    return get_item(article_json, args, site_json, save_debug)


def get_content(url, args, site_json, save_debug=False):
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

    item['image'] = ld_article['thumbnailUrl']

    item['summary'] = ld_article['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    gallery_html = ''
    page_lead = page_soup.find('div', class_='Page-lead')
    if page_lead:
        if page_lead.find('bsp-carousel'):
            item['_gallery'] = []
            gallery_html += '<h3><a href="{}/gallery?url={}" target="_blank">View gallery</a></h3>'.format(config.server, quote_plus(item['url']))
            gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            for i, slide in enumerate(page_lead.select('bsp-carousel div.Carousel-slide')):
                media = slide.find(class_='CarouselSlide-media')
                if 'imageSlide' in media['class']:
                    if media.img.get('data-flickity-lazyload-srcset'):
                        srcset = re.split(r'\s\dx,?', media.img['data-flickity-lazyload-srcset'])
                    else:
                        srcset = re.split(r'\s\dx,?', media.img['srcset'])
                    thumb = srcset[0]
                    src = srcset[1]
                    el = slide.find(class_='CarouselSlide-infoDescription')
                    if el and el.p:
                        caption = el.p.decode_contents().strip()
                    else:
                        caption = ''
                    if i == 0:
                        item['content_html'] += utils.add_image(src, caption)
                elif 'videoSlide' in media['class']:
                    player = media.find(['bsp-jw-player'])
                    video = jwplayer.get_content('https://cdn.jwplayer.com/v2/media/' + player['data-media-id'], {"embed": True}, {}, False)
                    if video:
                        src = video['_video_mp4']
                        thumb = '{}/image?url={}&width=800&overlay=video'.format(config.server, quote_plus(video['image']))
                        caption = video['summary']
                        if i == 0:
                            item['content_html'] += video['content_html']
                else:
                    logger.warning('unhandled CarouselSlide-media class ' + media['class'])
                    src = ''
                if src:
                    gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=src) + '</div>'
                    item['_gallery'].append({"src": src, "caption": caption, "thumb": thumb})
            if i % 2 == 0:
                gallery_html += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
            gallery_html += '</div>'

    ld_review = next((it for it in ld_json if it.get('review')), None)
    if ld_review and ld_review['review'].get('reviewRating'):
        item['content_html'] += utils.add_stars(float(ld_review['review']['reviewRating']['ratingValue']), int(ld_review['review']['reviewRating']['bestRating']))

    story_body = page_soup.select('main.Page-main > bsp-story-page > div.Page-storyBody > div.RichTextStoryBody')
    if story_body:
        body = story_body[0]
        for el in body.find_all(class_=['SovrnAd', 'optimizelyHubpeekClass']):
            el.decompose()

        for el in body.find_all(class_='Enhancement'):
            new_html = ''
            if el.find('bsp-list-loadmore'):
                el.decompose()
                continue
            elif el.find(class_='ImageEnhancement'):
                media = el.find('bsp-figure')
                if media:
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

        for el in body.find_all(class_='HTMLModuleEnhancement'):
            if el.find(class_='taboola_readmore'):
                el.decompose()
            else:
                logger.warning('unhandled HTMLModuleEnhancement in ' + item['url'])

        item['content_html'] += body.decode_contents()
        item['content_html'] = re.sub(r'</(div|figure|table)>\s*<(div|figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])

    if gallery_html:
        item['content_html'] += gallery_html

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    if split_url.path.startswith('/hub'):
        tag = split_url.path.split('/')[2]
        feed_url = 'https://afs-prod.appspot.com/api/v2/feed/tag?tags={}'.format(tag)
    else:
        feed_url = 'https://afs-prod.appspot.com/api/v2/feed/tag'

    feed_json = utils.get_url_json(feed_url)
    if not feed_json:
        return None
    if save_debug:
        utils.write_file(feed_json, './debug/debug.json')

    # Loop through each post
    n = 0
    items = []
    for card in feed_json['cards']:
        for content in card['contents']:
            url = 'https://afs-prod.appspot.com/api/v2/content/{}'.format(content['id'])
            if content['contentType'] == 'text':
                item = get_content(url, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        items.append(item)
            else:
                logger.warning('unhandled contentType {} in {}'.format(content['contentType'], url))

        for card_feed in card['feed']:
            for content in card_feed['contents']:
                url = 'https://afs-prod.appspot.com/api/v2/content/{}'.format(content['id'])
                if content['contentType'] == 'text':
                    item = get_content(url, args, site_json, save_debug)
                    if item:
                        if utils.filter_item(item, args) == True:
                            items.append(item)
                else:
                    logger.warning('unhandled contentType {} in {}'.format(content['contentType'], url))

    # sort by date
    items = sorted(items, key=lambda i: i['_timestamp'], reverse=True)

    feed = utils.init_jsonfeed(args)

    if 'max' in args:
        n = int(args['max'])
        feed['items'] = items[:n].copy()
    else:
        feed['items'] = items.copy()
    return feed
