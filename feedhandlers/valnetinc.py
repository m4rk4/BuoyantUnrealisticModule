import ast, html, json, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src.replace('&amp;', '&'))
    if split_url.path.startswith('/wordpresshttps'):
        img_src = img_src.replace(split_url.scheme + '://' + split_url.netloc + '/wordpress', '')
        return resize_image(img_src, width)
    if width > 0:
        if split_url.query:
            query = '?' + split_url.query
            # replace w
            query = re.sub(r'([\?&]w=)\d+', r'\1{}'.format(width), query)
            # remove h
            query = re.sub(r'[\?&]h=\d+', '', query)
        else:
            query = '?w={}'.format(width)
    elif width == 0:
        # Don't adjust size
        query = '?' + split_url.query
    else:
        # Full size
        if split_url.query:
            # remove w and h
            query = '?' + re.sub(r'[\?&][hw]=\d+', '', split_url.query)
            if query == '?':
                query = ''
        else:
            query = ''
    return split_url.scheme + '://' + split_url.netloc + split_url.path + query


def add_emaki_video(el):
    video_html = ''
    for m in re.findall(r'JSON\.parse\(`(.*?)`\)', str(el)):
        data = json.loads(m.replace('\\"', '"').replace("\\'", "'").replace('\\/', '/'))
        if data.get('playlist'):
            video_html = utils.add_video(data['playlist'][0]['url'], data['playlist'][0]['mimeType'], data['playlist'][0]['thumbnailLink'], data['playlist'][0]['title'], use_videojs=True)
    return video_html


def get_array_of_embeds(id, soup):
    el = soup.find('script', string=re.compile(r'window\.arrayOfEmbeds\["{}"\]'.format(id)))
    if not el:
        return None
    i = el.string.find('=') + 1
    m = re.search(r'^\s*(.*?);\s*window', el.string[i:])
    if not m:
        return None
    txt = m.group(1).replace('\\&quot;', '"').replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('\\/', '/')
    return ast.literal_eval(txt)


def get_content(url, args, site_json, save_debug=False):
    # Sites: https://www.valnetinc.com/en/publishing-detail#our_brand
    page_html = utils.get_url_html(url, site_json=site_json)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    page_soup = BeautifulSoup(page_html, 'lxml')
    ld_json = utils.get_ld_json(url, page_soup, site_json)
    if not ld_json:
        logger.warning('unable to find ld+json data in ' + url)
        return None
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    if 'NewsArticle' in ld_json:
        article_json = ld_json['NewsArticle']
    elif 'Article' in ld_json:
        article_json = ld_json['Article']
    elif 'VideoObject' in ld_json:
        article_json = ld_json['VideoObject']
    else:
        logger.warning('unknown ld+json article type in ' + url)
        return None

    item['id'] = urlsplit(article_json['url']).path.strip('/')
    item['url'] = article_json['url']

    if article_json.get('headline'):
        item['title'] = article_json['headline']
    elif article_json.get('name'):
        item['title'] = article_json['name']

    if article_json.get('datePublished'):
        dt = datetime.fromisoformat(article_json['datePublished'])
    elif article_json.get('uploadDate'):
        dt = datetime.fromisoformat(article_json['uploadDate']).astimezone(timezone.utc)
    else:
        dt = None
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('dateModified'):
        dt = datetime.fromisoformat(article_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    if article_json.get('author'):
        item['authors'] = [{"name": x['name']} for x in article_json['author']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    elif article_json.get('publisher'):
        item['author'] = {
            "name": article_json['publisher']['name']
            }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if article_json.get('articleSection'):
        item['tags'] += article_json['articleSection'].copy()
    for el in page_soup.find_all(class_='article-tags-name'):
        if el.get_text(strip=True) not in item['tags']:
            item['tags'].append(el.get_text(strip=True))
    if len(item['tags']) == 0:
        del item['tags']

    if article_json.get('thumbnailUrl'):
        item['image'] = article_json['thumbnailUrl']

    if article_json.get('description'):
        item['summary'] = article_json['description']

    if article_json['@type'] == 'VideoObject':
        item['content_html'] = utils.add_video(article_json['contentUrl'], 'video/mp4', item['image'], item['title'], use_videojs=True)
        if 'embed' not in args and 'summary' in item:
            item['content_html'] += '<p>' + item['summary'] + '</p>'
        return item

    item['content_html'] = ''
    el = page_soup.find(class_='article-header')
    if el:
        it = el.find('p', recursive=False)
        if it:
            item['content_html'] += '<p><em>' + it.decode_contents() + '</em></p>'
        if 'has_video' in el['class'] and el.find(class_='emaki-video-player'):
            item['content_html'] += add_emaki_video(el)
        else:
            it = el.select('.featured-embed > iframe')
            if it:
                item['content_html'] += utils.add_embed(it[0]['src'])
            else:
                it = el.find(class_='heading_image')
                if it:
                    if it.get('data-img-caption'):
                        caption = it['data-img-caption'].replace('\\/', '/').strip('"')
                    else:
                        caption = ''
                    item['content_html'] += utils.add_image(resize_image(it['data-img-url']), caption)
    
    el = page_soup.select('section#article-body > .content-block-regular')
    if el:
        body = el[0]
        for el in body.find_all(id='article-waypoint'):
            el.decompose()
        for el in body.find_all('span', class_='display-card-hyperlink-article'):
            el.unwrap()
        for el in body.find_all(['h2', 'h3'], id=True):
            el.attrs = {}
        for el in body.find_all('span', class_='small'):
            el.attrs = {}
            el.name = 'small'
        for el in body.find_all(class_='w-youtube'):
            new_html = utils.add_embed('https://www.youtube.com/watch?v=' + el['id'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        for el in body.find_all(class_='w-twitter'):
            new_html = utils.add_embed('https://x.com/__/status/' + el['id'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        for el in body.find_all(class_='w-instagram'):
            new_html = ''
            embed = get_array_of_embeds(el['id'], body)
            if embed:
                embed_soup = BeautifulSoup(embed['instagram'], 'html.parser')
                it = embed_soup.find('blockquote', class_='instagram-media')
                if it:
                    new_html = utils.add_embed(it['data-instgrm-permalink'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled w-instagram embed in ' + item['url'])
        for el in body.find_all('blockquote', class_=False, recursive=False):
            el.attrs = {}
            el['style'] = config.blockquote_style
        for el in body.find_all(class_='emaki-custom-block'):
            new_html = ''
            if 'emaki-custom-note' in el['class']:
                new_html = '<div style="border:4px solid #ffd10f; border-radius:10px; background-color:light-dark(#ccc,#333); padding:1em; margin:1em 0;"><div><b>Note</b></div>'
                it = el.find(class_='note')
                if it:
                    new_html += it.decode_contents()
                new_html += '</div>'
            elif 'emaki-custom-tip' in el['class']:
                new_html = '<div style="border:4px solid #8789c0; border-radius:10px; background-color:light-dark(#ccc,#333); padding:1em; margin:1em 0;"><div><b>Tip</b></div>'
                it = el.find(class_='tip')
                if it:
                    new_html += it.decode_contents()
                new_html += '</div>'
            elif 'emaki-custom-warning' in el['class']:
                new_html = '<div style="border:4px solid #e01a4f; border-radius:10px; background-color:light-dark(#ccc,#333); padding:1em; margin:1em 0;"><div><b>Warning</b></div>'
                it = el.find(class_='warning')
                if it:
                    new_html += it.decode_contents()
                new_html += '</div>'
            elif 'emaki-custom-key-points' in el['class']:
                new_html = '<div style="border-radius:10px; background-color:light-dark(#ccc,#333); padding:1em; margin:1em 0;"><div><b>'
                it = el.find(class_='title')
                if it:
                    new_html += it.get_text(strip=True).strip(':')
                else:
                    new_html += 'Summary'
                new_html += '</b></div>'
                it = el.find(class_='custom_block-content')
                if it:
                    new_html += it.decode_contents()
                new_html += '</div>'
            elif 'emaki-custom-pullquote' in el['class']:
                it = el.find(class_='pullquote')
                if it:
                    new_html += utils.add_pullquote(it.decode_contents())
            elif 'emaki-custom-promoted' in el['class']:
                new_html = '<div style="border:4px solid #e0f1d7; border-radius:10px; background-color:light-dark(#ccc,#333); padding:1em; margin:1em 0;"><div><b>Promoted</b></div>'
                it = el.find(class_='promoted')
                if it:
                    new_html += it.decode_contents()
                new_html += '</div>'
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled {} in {}'.format(el['class'], item['url']))
        for el in body.find_all(class_='display-card'):
            new_html = ''
            if 'article-card' in el['class']:
                it = el.find('label')
                if it:
                    caption = it.get_text(strip=True).lower()
                    if caption == 'related' or caption == 'next':
                        el.decompose()
                        continue
            # elif 'tag' in el['class']:
            # elif 'type-screen' in el['class']:
            elif 'video' in el['class'] and el.find(class_='emaki-video-player'):
                new_html = add_emaki_video(el)
            elif ('type-video-game' in el['class'] or 'type-screen' in el['class']) and ('large' in el['class'] or 'medium' in el['class']):
                new_html = '<div style="border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:light-dark(#ccc,#333); padding:1em; margin:1em 0;">'
                it = el.find(class_='display-card-title')
                if it:
                    new_html += '<div style="font-size:larger; font-weight:bold; margin-bottom:1em;">' + it.get_text(strip=True) + '</div>'
                else:
                    it = el.find(class_='content-title')
                    if it:
                        new_html += '<div style="font-size:larger; font-weight:bold; margin-bottom:1em;">' + it.get_text(strip=True) + '</div>'
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;;">'
                it = el.find(class_='image-column')
                if it:
                    it = it.find(class_='responsive-img')
                    if it:
                        new_html += '<div style="flex:1; min-width:256px;"><img src="' + resize_image(it['data-img-url'], 800) + '" style="width:100%;"></div>'
                new_html += '<div style="flex:2; min-width:256px;">'
                if el.find(class_='w-rating'):
                    it = el.find(class_=['rate-number', 'review-rating'])
                    if it:
                        m = re.search(r'^[\d\.]+', it.get_text(strip=True))
                        if m:
                            new_html += utils.add_score_gauge(10 * float(m.group(0)), m.group(0))
                it = el.find(class_='dc-movie-rating')
                if it:
                    movie_rating = it.get_text(strip=True)
                else:
                    movie_rating = ''
                if el.select('.w-display-card-info > dl'):
                    new_html += '<dl style="display:grid; grid-gap:4px 16px; grid-template-columns:max-content; font-size:smaller;">'
                    for it in el.select('.w-display-card-info > dl'):
                        for x in it.select('div:has(> dd.rating)'):
                            x.decompose()
                        if el.find(class_='fx-ratings__summary--content'):
                            x = it.select('div:has(dt > strong:-soup-contains("Review Summary"))')
                            if x[0]:
                                x[0].decompose()
                        for x in it.find_all('div', recursive=False):
                            x.unwrap()
                        for x in it.select('a.open-critics-logo > img'):
                            x.decompose()
                        if movie_rating:
                            it.insert(0, BeautifulSoup('<dt><strong>Rated</strong></dt><dd>' + movie_rating + '</dd>', 'html.parser'))
                            movie_rating = ''
                        for x in it.find_all('dd'):
                            x.attrs = {}
                            x['style'] = 'margin:0; grid-column-start:2;'
                        new_html += it.decode_contents()
                    new_html += '</dl>'
                elif movie_rating:
                    new_html += '<dl style="display:grid; grid-gap:4px 16px; grid-template-columns:max-content; font-size:smaller;"><dt><strong>Rated</strong></dt><dd style="margin:0; grid-column-start:2;">' + movie_rating + '</dd></dl>'
                if el.select('.w-where-to-watch ul > li > a'):
                    new_html += '<div style="display:flex; align-items:center; justify-content:center; gap:1em; margin-top:1em;">'
                    links = []
                    for it in el.select('.w-where-to-watch ul > li > a'):
                        link = it['href']
                        if link.startswith('https://redirect.viglink.com'):
                                params = parse_qs(urlsplit(link).query)
                                if 'u' in params:
                                    link = params['u'][0]
                        if link not in links:
                            links.append(link)
                            new_html += '<a href="' + link + '" target="_blank"><img src="' + resize_image(it.img['data-img-url'], 0) + '" style="width:36px; height:36px;"/></a>'
                    new_html += '</div>'
                new_html += '</div></div>'
                it = el.find(class_='fx-ratings__summary--content')
                if it:
                    new_html += '<div><b>Review Summary</b></div>' + it.decode_contents()
                if el.find(class_='fx-rating__list'):
                    for it in el.select('.fx-rating__list > .fx-rating__bar'):
                        x = it.find('progress')
                        if x:
                            caption = re.sub(r'[\d\.]+$', '', it.get_text(strip=True))
                            new_html += utils.add_bar(caption, float(x['value']), float(x['max']), show_percent=False)
                if el.select('.display-card-pros-cons-content ul.pro-list'):
                    new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; margin-top:1em;">'
                    it = el.select('.display-card-pros-cons-content ul.pro-list')
                    if it:
                        for x in it[0].find_all('li'):
                            x.attrs = {}
                        new_html += '<div style="flex:1; min-width:256px;"><div><b>Pros:</b></div><ul style=\'color:ForestGreen; list-style-type:"✓&nbsp;"\'>' + it[0].decode_contents() + '</ul></div>'
                    it = el.select('.display-card-pros-cons-content ul.con-list')
                    if it:
                        for x in it[0].find_all('li'):
                            x.attrs = {}
                        new_html += '<div style="flex:1; min-width:256px;"><div><b>Cons:</b></div><ul style=\'color:Maroon; list-style-type:"✗&nbsp;"\'>' + it[0].decode_contents() + '</ul></div>'
                    new_html += '</div>'
                if el.select('ul.cast-tab-list > li.cast-tab'):
                    new_html += '<div style="margin:1em 0 0.5em 0;">'
                    it = el.select('.w-cast-info > a')
                    if it:
                        new_html += '<a href="' + it[0]['href'] + '" target="_blank"><b>Cast</b></a>'
                    else:
                        new_html += '<b>Cast</b>'
                    new_html += '</div><div style="display:flex; flex-wrap:wrap; align-items:center; gap:1em; font-size:smaller;">'
                    for it in el.select('ul.cast-tab-list > li.cast-tab'):
                        new_html += '<div style="display:flex; align-items:center; gap:8px;"><img src="' + resize_image(it.img['data-img-url'], 0) + '" style="height:4em;"><div><b>' + it.find(class_='cast-name').get_text(strip=True) + '</b><br/>' + it.find(class_='cast-info').get_text(strip=True) + '</div></div>'
                    new_html += '</div>'
                if el.find(class_='valnet-gallery') or el.select('.w-display-card-video-trailer > video'):
                    new_html += '<div style="display:flex; flex-wrap:wrap; justify-content:center; gap:1em; margin-top:1em;">'
                    if el.find(class_='valnet-gallery'):
                        gallery_images = []
                        images = el.select('.valnet-gallery .gallery__images__item')
                        for it in images:
                            if it.get('data-img-caption'):
                                caption = it['data-img-caption'].replace('\\/', '/').strip('"')
                            else:
                                caption = ''
                            gallery_images.append({"src": resize_image(it['data-img-url'], -1), "caption": caption, "thumb": resize_image(it['data-img-url'], 640)})
                        gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images))
                        caption = '<a href="' + gallery_url + '" target="_blank">View gallery (' + str(len(images)) + ' images)</a>'
                        new_html += utils.add_image(resize_image(gallery_images[0]['src']), caption, link=gallery_url, fig_style='flex-basis:240px; margin:0; padding:0;', figcap_style='text-align:center;', overlay=config.gallery_button_overlay)
                    it = el.select('.w-display-card-video-trailer > video')
                    if it:
                        caption = '<a href="' + config.server + '/videojs?src=' + quote_plus(it[0].source['src']) + '&type=' + quote_plus(it[0].source['type']) + '" target="_blank">Watch trailer</a>'
                        new_html += utils.add_video(it[0].source['src'], it[0].source('type'), it[0]['poster'], caption, fig_style='flex-basis:240px; margin:0; padding:0;', figcap_style='text-align:center;', use_videojs=True)
                new_html += '</div>'
            elif 'type-generic' in el['class']:
                # print(str(el))
                card_footer = ''
                it = el.find(class_='display-card-description')
                if it and it.decode_contents().strip():
                    print('\n\n' + str(it))
                    card_footer += '<p style="font-size:smaller;">' + it.decode_contents().strip() + '</p>'
                card_image = ''
                it = el.find(class_='image-column')
                if it:
                    it = it.find(class_='responsive-img')
                    if it:
                        card_image = '<div style="width:100%; height:100%; background:url(\'' + resize_image(it['data-img-url'], 240) + '\'); background-position:center; background-size:cover; '
                        if card_footer:
                            card_image += 'border-radius:10px 0 0 0;"></div>'
                        else:
                            card_image += 'border-radius:10px 0 0 10px;"></div>'
                card_content = ''
                it = el.find(class_='display-card-title')
                if it:
                    card_content += '<div style="font-weight:bold; margin-bottom:4px;">' + it.get_text(strip=True) + '</div>'
                it = el.find(class_='display-item-price')
                if it:
                    x = it.find('span', class_='regular-price')
                    if x:
                        x.attrs = {}
                        x.name = 's'
                    card_content += '<div style="font-size:small; margin-bottom:4px;">' + it.decode_contents() + '</div>'
                if el.select('.w-display-card-info > dl'):
                    card_content += '<dl style="display:grid; grid-gap:4px 16px; grid-template-columns:max-content; font-size:small;">'
                    for it in el.select('.w-display-card-info > dl'):
                        for x in it.find_all('div', recursive=False):
                            x.unwrap()
                        for x in it.find_all('dd'):
                            x.attrs = {}
                            x['style'] = 'margin:0; grid-column-start:2;'
                        card_content += it.decode_contents()
                    card_content += '</dl>'
                for it in el.select('.display-card-affiliate-links > .w-display-card-link > a'):
                    if card_footer:
                        card_footer += utils.add_button(it['href'], it.get_text(strip=True), font_size='smaller')
                    else:
                        card_content += utils.add_button(it['href'], it.get_text(strip=True), font_size='smaller')
                if 'small' in el['class']:
                    new_html = utils.format_small_card(card_image, card_content, card_footer, image_width='120px', image_height='100%', content_style='padding:8px;', align_items='start', min_width='240px', max_width='360px')
                elif 'medium' in el['class']:
                    new_html = utils.format_small_card(card_image, card_content, card_footer, image_width='180px', image_height='100%', content_style='padding:8px;', align_items='start', min_width='360px', max_width='540px')
                elif 'large' in el['class']:
                    new_html = utils.format_small_card(card_image, card_content, card_footer, image_width='240px', image_height='100%', content_style='padding:8px;', align_items='start', min_width='480px', max_width='720px')
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled {} in {}'.format(el['class'], item['url']))
        for el in body.find_all(class_='w-play_store_app'):
            new_html = ''
            embed = get_array_of_embeds(el['id'], body)
            if embed:
                embed_soup = BeautifulSoup(embed['play_store_app'], 'html.parser')
                it = embed_soup.find('a', class_='app-widget-name')
                if it:
                    card_image = ''
                    card_content = ''
                    if embed_soup.img:
                        card_image = '<a href="' + it['href'] + '" target="_blank"><div style="width:100%; height:100%; background:url(\'' + embed_soup.img['src'] + '\'); background-position:center; background-size:cover; border-radius:10px 0 0 10px;"></div></a>'
                    card_content += '<div style="font-weight:bold; margin-bottom:4px;"><a href="' + it['href'] + '" target="_blank">' + it.get_text(strip=True) + '</a></div>'
                    it = embed_soup.find('a', class_='app-widget-developper')
                    if it:
                        card_content += '<div style="font-size:small; margin-bottom:4px;"><a href="' + it['href'] + '" target="_blank">' + it.get_text(strip=True) + '</a></div>'
                    it = embed_soup.find(class_='app-genre')
                    if it:
                        card_content += '<div style="font-size:small;">' + it.get_text(strip=True) + '</div>'
                    it = embed_soup.find(class_='app-widget-price')
                    if it:
                        card_content += '<div style="font-size:small;">' + it.get_text(strip=True) + '</div>'
                    it = embed_soup.find(class_=re.compile(r'^app-widget-rating'))
                    if it:
                        card_content += '<div style="font-size:small;">Rating: ' + it.get_text(strip=True) + '</div>'
                    new_html += utils.format_small_card(card_image, card_content, '', image_size='128px', content_style='padding:8px;', align_items='start')
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled {} in {}'.format(el['class'], item['url']))
        for el in body.find_all(class_='valnet-gallery'):
            new_html = ''
            it = el.find('script', string=re.compile(r'window\.arrayOfGalleries'), attrs={"type": "module"})
            if it:
                i = it.string.find("'") + 1
                j = it.string.rfind("'")
                # gallery_html = html.unescape(it.string[i:j]).strip('"')
                gallery_html = it.string[i:j].replace('\\&quot;', '"').replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('\\/', '/').strip('"')
                if save_debug:
                    utils.write_file(gallery_html, './debug/gallery.html')
                gallery_soup = BeautifulSoup(gallery_html, 'html.parser')
                gallery_images = []
                images = gallery_soup.find_all(class_='splide__slide')
                for slide in images:
                    captions = []
                    it = slide.find('figcaption')
                    if it and it.get_text(strip=True):
                        captions.append(it.decode_contents().strip())
                    it = slide.find(class_='body-img-caption')
                    if it and it.get_text(strip=True):
                        captions.append(it.decode_contents().strip())
                    gallery_images.append({"src": resize_image(slide.img['data-img-url'], -1), "caption": ' | '.join(captions), "thumb": resize_image(slide.img['data-img-url'], 640)})
                gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images))
                caption = '<a href="' + gallery_url + '" target="_blank">View gallery (' + str(len(images)) + ' images)</a>'
                new_html = utils.add_image(resize_image(gallery_images[0]['src']), caption, link=gallery_url, overlay=config.gallery_button_overlay)
            elif el.find(class_='article__gallery'):
                new_html = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                images = el.select('.article__gallery .gallery__images__item')
                for slide in images:
                    if slide.get('data-img-caption'):
                        caption = slide['data-img-caption'].replace('\\/', '/').strip('"')
                    else:
                        caption = ''
                    new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(resize_image(slide['data-img-url']), caption, link=resize_image(slide['data-img-url'], -1), fig_style='margin:0; padding:0;') + '</div>'
                new_html += '</div>'
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled valnet-gallery in ' + item['url'])
        for el in body.select('.table-container:has(ul.column-to-list > li > td > .body-img)'):
            new_html = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
            images = el.select('.body-img > .responsive-img')
            for slide in images:
                if slide.get('data-img-caption'):
                    caption = slide['data-img-caption'].replace('\\/', '/').strip('"')
                else:
                    caption = ''
                new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(resize_image(slide['data-img-url']), caption, link=resize_image(slide['data-img-url'], -1), fig_style='margin:0; padding:0;') + '</div>'
            new_html += '</div>'
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled table-container in ' + item['url'])
        for el in body.find_all(class_='body-img'):
            it = el.find(class_='responsive-img')
            if it:
                if it.get('data-img-caption'):
                    caption = it['data-img-caption'].replace('\\/', '/').strip('"')
                else:
                    caption = ''
                new_el = BeautifulSoup(utils.add_image(resize_image(it['data-img-url']), caption), 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled body-img in ' + item['url'])
        for el in body.select('h2:has(> span.item-num)'):
            it = el.find('span', class_='item-num')
            new_html = '<h2 style="width:100%; text-align:center; border-bottom:4px solid ' + config.text_color + '; line-height:1px; margin:2em 0 1em 0;"><span style="background-color:' + config.background_color + '; padding:0.5em;">' + it.get_text(strip=True) + '</span></h2><h2>'
            it.decompose()
            new_html += el.get_text(strip=True) + '</h2>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in body.find_all('script'):
            el.decompose()
        for el in body.find_all(text=lambda text: isinstance(text, Comment)):
            el.extract()

        item['content_html'] += body.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
