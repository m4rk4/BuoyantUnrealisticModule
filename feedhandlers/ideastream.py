import html, math, json, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_audio_info(el_audio):
    audio_src = ''
    audio_type = ''
    audio_name = ''
    duration = ''
    el = el_audio.find('ps-stream-url')
    if el:
        audio_src = el['data-stream-url']
        audio_type = el.get('data-stream-format')
        if not audio_type and 'mp3' in el['data-stream-url']:
            audio_type = 'audio/mpeg'
    el = el_audio.find('ps-stream')
    if el:
        if el.get('data-stream-name'):
            audio_name = el['data-stream-name']
            duration = el['data-stream-duration']
    return audio_src, audio_type, audio_name, duration


def get_image(el_image):
    img = el_image.find('img')
    images = []
    if img.has_attr('srcset'):
        for it in img['srcset'].split(','):
            img_src = it.split(' ')[0]
            m = re.search(r'\/resize\/(\d+)x(\d+)', img_src)
            if m:
                image = {}
                image['src'] = img_src
                image['width'] = int(m.group(1))
                image['height'] = int(m.group(2))
                images.append(image)
    if img.has_attr('data-src'):
        img_src = img['data-src']
        m = re.search(r'\/resize\/(\d+)x(\d+)', img_src)
        if m:
            image = {}
            image['src'] = img_src
            image['width'] = int(m.group(1))
            image['height'] = int(m.group(2))
            images.append(image)
    if img.has_attr('loading'):
        img_src = img['src']
        if img['loading'] != 'lazy':
            m = re.search(r'\/resize\/(\d+)x(\d+)', img_src)
            if m:
                image = {}
                image['src'] = img_src
                image['width'] = int(m.group(1))
                image['height'] = int(m.group(2))
                images.append(image)
    if images:
        qs = parse_qs(urlsplit(images[0]['src']).query)
        if qs and qs.get('url'):
            m = re.search(r'\/crop\/(\d+)x(\d+)', images[0]['src'])
            if m:
                image = {}
                image['src'] = qs['url'][0]
                image['width'] = int(m.group(1))
                image['height'] = int(m.group(2))
                images.append(image)
        img = utils.closest_dict(images, 'width', 1000)
        img_src = img['src']

    caption = []
    it = el_image.find(class_='Figure-caption')
    if it:
        text = it.get_text().strip()
        if text and text != '.':
            caption.append(text)
    else:
        it = el_image.find('figcaption')
        if it:
            text = it.get_text().strip()
            if text and text != '.':
                caption.append(text)

    it = el_image.find(class_='Figure-credit')
    if it:
        text = it.get_text().strip()
        if text:
            caption.append(text)
    else:
        it = el_image.find(class_='credit')
        if it:
            text = it.get_text().strip()
            if text:
                caption.append(text)

    it = el_image.find(class_='Figure-source')
    if it:
        text = it.get_text().strip()
        if text:
            caption.append(text)
    return img_src, ' | '.join(caption)


def add_carousel(carousel, n=0):
    # n = 1 : first slide only
    # n = 0 : all slides
    # n = -1 : exclude first slide
    carousel_html = ''
    for i, slide in enumerate(carousel.find_all(class_='Carousel-slide')):
        if n == 0 or (n == 1 and i == 0) or (n == -1 and i > 0):
            captions = []
            it = slide.find(class_='CarouselSlide-infoDescription')
            if it:
                captions.append(it.decode_contents())
            it = slide.find(class_='CarouselSlide-infoAttribution')
            if it:
                captions.append(it.decode_contents())
            img_src = ''
            it = slide.find('img')
            if it:
                if it.get('data-flickity-lazyload'):
                    img_src = it['data-flickity-lazyload']
                elif it.get('src'):
                    img_src = it['src']
            if img_src:
                carousel_html += utils.add_image(img_src, ' | '.join(captions))
            else:
                logger.warning('unknown Carousel-slide img src')
    return carousel_html


def get_content(url, args, site_json, save_debug=False):
    article_html = utils.get_url_html(url)
    if not article_html:
        return None

    soup = BeautifulSoup(article_html, 'html.parser')
    el = soup.find('meta', attrs={"name": "brightspot-dataLayer"})
    if not el:
        logger.warning('unable to find brightspot-dataLayer')
        return None

    data_json = json.loads(html.unescape(el['content']))
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')
        utils.write_file(article_html, './debug/debug.html')

    item = {}
    if data_json.get('nprStoryId'):
        item['id'] = data_json['nprStoryId']
    elif data_json.get('Content_ID'):
        item['id'] = data_json['Content_ID']
    elif data_json.get('Chorus_UID'):
        item['id'] = data_json['Chorus_UID']

    item['url'] = url

    if data_json.get('storyTitle'):
        item['title'] = data_json['storyTitle']
    else:
        el = soup.find('meta', attrs={"property": "og:title"})
        if el:
            item['title'] = el['content']

    # This seems to correspond to the rss feed date
    dt = None
    el = soup.find('meta', attrs={"property": "article:published_time"})
    if el:
        if el['content'].endswith('Z'):
            date = el['content'].replace('Z', '+00:00')
        else:
            date = re.sub(r'\.\d\d$', '', el['content']) + '+00:00'
        dt = datetime.fromisoformat(date)
    elif data_json.get('publishDate'):
        dt = datetime.fromisoformat(data_json['publishedDate'].replace('Z', '+00:00'))
    elif data_json.get('Publish_Date'):
        # https://chicago.suntimes.com/afternoon-edition-newsletter/2023/10/16/23919786/afternoon-edition
        tz_est = pytz.timezone('US/Eastern')
        dt_est = dateutil.parser.parse(data_json['Publish_Date'])
        dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    dt = None
    el = soup.find('meta', attrs={"property": "article:modified_time"})
    if el:
        if el['content'].endswith('Z'):
            date = el['content'].replace('Z', '+00:00')
        else:
            date = re.sub(r'\.\d\d$', '', el['content']) + '+00:00'
        dt = datetime.fromisoformat(date)
    elif data_json.get('Last_Time_Updated'):
        tz_est = pytz.timezone('US/Eastern')
        dt_est = dateutil.parser.parse(data_json['Last_Time_Updated'])
        dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    if dt:
        item['date_modified'] = dt.isoformat()

    authors = []
    if data_json.get('author'):
        authors = [it.strip() for it in data_json['author'].split(',')]
    elif data_json.get('Author'):
        authors = [it.strip() for it in data_json['Author'].split(',')]
    el = soup.find(class_=['ArticlePage-authorBy', 'AuthorByline-InPage'])
    if el:
        it = el.find('a')
        if it:
            author = it.get_text().strip()
        else:
            author = re.sub('^By\s+(.*)', r'\1', el.get_text().strip())
        if author not in authors:
            authors.append(author)
    for el in soup.find_all(class_='ArticlePage-contributors'):
        it = el.find('a')
        if it:
            author = it.get_text().strip()
        else:
            author = re.sub('^Contributors:\s+(.*)', r'\1', el.get_text().strip())
        if author not in authors:
            authors.append(author)
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if data_json.get('keywords'):
        item['tags'] = [it.strip() for it in data_json['keywords'].split(',')]
    elif data_json.get('Keywords'):
        item['tags'] = [it.strip() for it in data_json['Keywords'].split(',')]

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']

    el = soup.find('meta', attrs={"property": "og:description"})
    if el:
        item['summary'] = el['content']

    item['content_html'] = ''
    lede_img = False
    gallery = ''
    for el in soup.find_all(class_=['ArticlePage-lead', 'ArticlePage-lede', 'ArtP-lead', 'LongFormPage-lead',  'lead']):
        if el.find(class_=['VideoEnhancement', 'VideoEnh']):
            it = el.find(class_='YouTubeVideoPlayer')
            if it:
                item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + it['data-video-id'])
                lede_img = True
            else:
                logger.warning('unhandled VideoEnh in ArtP-lead in ' + item['url'])
        elif el.find(class_='Carousel'):
            it = el.find(class_='Carousel')
            item['content_html'] += add_carousel(it, 1)
            gallery = '<h2>Gallery</h2>' + add_carousel(it, -1)
            lede_img = True
        elif el.find(class_='ArticlePage-lede-content'):
            it = el.find(class_='Page-subHeadline')
            if it:
                item['content_html'] += '<p><em>{}</em></p>'.format(it.get_text())
        else:
            img_src, caption = get_image(el)
            item['content_html'] += utils.add_image(img_src, caption)
            lede_img = True

    if not lede_img and item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'])

    el = soup.find(class_=['ArticlePage-audioPlayer', 'ArtP-audioPlayer', 'audioPlayer', 'LongFormPage-audioPlayer'])
    if el:
        audio_src, audio_type, audio_name, duration = get_audio_info(el)
        if audio_src:
            attachment = {}
            attachment['url'] = audio_src
            attachment['mime_type'] = audio_type
            item['attachments'] = []
            item['attachments'].append(attachment)
            item['_audio'] = audio_src
            item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen ({2})</a></span></div>'.format(audio_src, config.server, duration)

    article = soup.find(class_=['ArticlePage-articleBody', 'ArtP-articleBody', 'LongFormPage-articleBody', 'articleBody', 'RichTextArticleBody'])

    for el in article.find_all(class_=['Enh', 'Enhancement']):
        new_html = ''
        if el.find(class_=['Quote-wrapper', 'QuoteEnhancement']):
            it = el.find(class_=['Quote-attribution', 'attribution'])
            if it:
                author = it.get_text()
                it.decompose()
            else:
                author = ''
            it = el.find(class_='Quote')
            if it.name == 'blockquote':
                new_html = utils.add_pullquote(it.get_text(), author)
            else:
                new_html = utils.add_pullquote(it.blockquote.get_text(), author)

        elif el.find(class_='AudioEnhancement'):
            audio_src, audio_type, audio_name, duration = get_audio_info(el)
            desc = ''
            it = el.find(class_='AudioEnhancement-description')
            if it:
                desc += ' &ndash; {}'.format(el.get_text().strip())
            if not desc and audio_name:
                desc += ' &ndash; {}'.format(audio_name)
            new_html = '<blockquote><h4><a style="text-decoration:none;" href="{0}">&#9658;</a>&nbsp;<a href="{0}">Listen</a>{1} ({2})</h4></blockquote>'.format( audio_src, desc, duration)

        elif el.find(class_='Figure'):
            img_src, caption = get_image(el)
            new_html = utils.add_image(img_src, caption)

        elif el.find(attrs={"data-size": "articleImage"}):
            img_src, caption = get_image(el)
            new_html = utils.add_image(img_src, caption)

        elif el.find(class_='Carousel'):
            new_html = add_carousel(el)

        elif el.find(class_='twitter-tweet'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])

        elif el.find(class_='instagram-media'):
            it = el.find('blockquote', class_='instagram-media')
            new_html = utils.add_embed(it['data-instgrm-permalink'])

        elif el.find('iframe'):
            new_html = utils.add_embed(el.iframe['src'])

        elif el.find(class_='HtmlModule'):
            if el.find(id=re.compile(r'om-\w+-holder')):
                el.decompose()
                continue

        elif 'RatingCard' in el['class']:
            # https://chicago.suntimes.com/2023/10/11/23909969/fall-house-usher-review-netflix-series-bruce-greenwood-carla-gugino-edgar-allan-poe
            new_html += '<div style="border:1px solid black; border-radius:10px; margin-left:auto; margin-right:auto; max-width:400px; padding:8px;">'
            it = el.find(class_='RatingCard-title')
            if it:
                new_html += '<div style="font-size:1.1em; font-weight:bold; text-align:center;">{}</div>'.format(it.get_text())
            if el.get('data-rating'):
                new_html += '<div style="font-size:2em; text-align:center;"><span style="color:red; font-weight:bold;">'
                rating = float(el['data-rating'])
                for i in range(math.floor(rating)):
                    new_html += '★'
                if rating % 1 > 0:
                    new_html += '½'
                new_html += '</span>'
                if math.ceil(rating) < 4:
                    for i in range(4 - math.ceil(rating)):
                        new_html += '☆'
                new_html += '</div>'
            new_html += '</div>'

        elif 'RichTextSidebarModule' in el['class']:
            text = ''
            it = el.find(class_='RichTextSidebarModule-title')
            if it and it.get_text().strip() != 'Untitled':
                text += '<div style="font-size:1.1em; font-weight:bold;">{}</div>'.format(it.get_text().strip())
            it = el.find(class_='RichTextModule-items')
            if it:
                text += it.decode_contents()
            new_html += utils.add_blockquote(text)

        elif el.find('ps-promo'):
            el.decompose()
            continue

        elif el.find(class_=['AdModule', 'SendGridSubscribe']):
            el.decompose()
            continue

        elif el.find_all('h3', string=re.compile(r'Related Stories', flags=re.I)):
            el.decompose()
            continue

        else:
            logger.warning('unhandled Enhancement in ' + url)
            #print(el)

        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in article.find_all(class_='fullattribution'):
        it = el.find('img')
        if it and it.has_attr('src') and 'google-analytics' in it['src']:
            it.decompose()

    for el in article.find_all(class_='news-coda'):
        el.decompose()

    for el in article.find_all(class_='RTEHashTagLabAdModule'):
        el.decompose()

    for el in article.find_all('script'):
        el.decompose()

    item['content_html'] += str(article) + gallery
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.rss'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')

    n = 0
    feed_items = []
    for el in soup.find_all(class_=re.compile(r'Promo[A-C]-title|List[A-C]-items-item')):
        if save_debug:
            logger.debug('getting content for ' + el.a['href'])
        item = get_content(el.a['href'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    #feed['title'] = 'Stories - PGA of America'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
