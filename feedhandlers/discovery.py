import json, math, re
import dateutil.parser
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, size='full'):
    orig_src = re.sub(r'\.rend\..*', '', img_src)
    if size == 'orig':
        return orig_src
    m = re.search(r'\.rend\.([^\.]+)\.(\d+)\.(\d+)(\.\d+)?\.suffix\/(.*)', img_src)
    w = int(m.group(2))
    h = int(m.group(3))
    if size == 'thumb':
        if w >= h:
            return orig_src + '.rend.{}.791.594.85.suffix/{}'.format(m.group(1), m.group(5))
        else:
            return orig_src + '.rend.{}.616.822.85.suffix/{}'.format(m.group(1), m.group(5))
    else:
        if w >= h:
            return orig_src + '.rend.{}.1280.960.85.suffix/{}'.format(m.group(1), m.group(5))
        else:
            return orig_src + '.rend.{}.1280.1600.85.suffix/{}'.format(m.group(1), m.group(5))


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    clean_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
    if clean_url.endswith('/'):
        clean_url = clean_url[:-1]

    #content_json = utils.get_url_json(clean_url + '.lazy-fetch.json')
    data_json = utils.get_url_json(clean_url + '.json', use_proxy=True, use_curl_cffi=True)
    if not data_json:
        return None
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')

    if 'photoGalleryPage' in data_json['cq:template']:
        content_html = utils.get_url_html(clean_url, use_proxy=True, use_curl_cffi=True)
    else:
        content_html = utils.get_url_html(clean_url + '.lazy-fetch-html-content.html', use_proxy=True, use_curl_cffi=True)

    if not content_html:
        return None
    if save_debug:
        utils.write_file(content_html, './debug/debug.html')
    soup = BeautifulSoup(content_html, 'html.parser')

    item = {}
    item['id'] = data_json['jcr:uuid']
    item['url'] = clean_url
    if data_json.get('sni:seoTitle'):
        item['title'] = data_json['sni:seoTitle']
    elif data_json.get('sni:title'):
        item['title'] = data_json['sni:title']

    dt = dateutil.parser.parse(data_json['sni:origPubDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = dateutil.parser.parse(data_json['cq:lastModified']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for el in soup.find_all(class_='o-Attribution__a-Name'):
        if el.get_text().strip() not in authors:
            authors.append(el.get_text().strip())
    if authors:
        item['authors'] = [{"name": x} for x in authors]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        }

    item['tags'] = []
    for el in soup.find_all('a', class_='a-Tag'):
        item['tags'].append(el.get_text().strip())
    if not item.get('tags'):
        del item['tags']

    if data_json.get('sni:images'):
        item['image'] = site_json['image_server'] + data_json['sni:images'][0]
    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['image'] = el['content']

    el = soup.find('meta', attrs={"name": "description"})
    if el:
        item['summary'] = el['content']

    item['content_html'] = ''
    el = soup.select('section.o-AssetDescription > div.o-AssetDescription__a-Description')
    if el:
        if el[0].p:        
            item['content_html'] += '<p><em>' + el[0].p.decode_contents() + '</em></p>'
        else:
            item['content_html'] += '<p><em>' + el[0].decode_contents() + '</em></p>'

    el = soup.find('script', attrs={"type": "application/ld+json"})
    if el:
        ld_json = json.loads(el.string)
    else:
        ld_json = None

    if 'photoGalleryPage' in data_json['cq:template']:
        item['content_html'] += '<h3><a href="{}/gallery?url={}">View slideshow</a></h3>'.format(config.server, quote_plus(item['url']))
        item['_gallery'] = []
        if ld_json:
            el = soup.find(class_='slide', attrs={"hx-get": True})
            slide_url = 'https://' + split_url.netloc + el['hx-get']
            for slide in ld_json[0]['mainEntity']['itemListElement']:
                img_src = slide['item']['image']
                thumb = resize_image(img_src, 'thumb')
                caption = ''
                desc = '<h3>' + slide['item']['name'] + '</h3>'
                link = ''
                slide_url = re.sub(r'/images-\d+', '/images-' + str(slide['position']), slide_url)
                slide_html = utils.get_url_html(slide_url, use_proxy=True, use_curl_cffi=True)
                if slide_html:
                    slide_soup = BeautifulSoup(slide_html, 'html.parser')
                    el = slide_soup.find(class_='slide-credit')
                    if el:
                        caption = el.get_text().strip()
                    el = slide_soup.find(class_='slide-caption')
                    if el:
                        desc += el.decode_contents()
                    el = slide_soup.find('a', class_='slide-cta')
                    if el:
                        link = config.server + '/content?read&url=' + quote_plus('https:' + el['href'])
                        desc += utils.add_button(link, el.get_text().strip())
                else:
                    desc += '<p>' + slide['item']['description'] + '</p>'
                item['content_html'] += utils.add_image(img_src, caption, link=link, desc=desc) + '<div>&nbsp;</div>'
                item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})
        return item
    elif 'recipePage' in data_json['cq:template']:
        if data_json.get('sni:videos'):
            el = soup.select('section.o-RecipeLead script[type="text/x-config"]')
            if el:
                video_json = json.loads(el[0].string)
                video_src = 'https://' + split_url.netloc + '/apps/api/playback?path=' + video_json['webPlayer']['channels'][0]['videos'][0]['path']
                poster = site_json['image_server'] + video_json['webPlayer']['channels'][0]['videos'][0]['posterImage']
                item['content_html'] += utils.add_video(video_src, 'application/x-mpegURL', poster)
        else:
            el = soup.select('section.o-RecipeLead img.a-Image')
            if el:
                img_src = resize_image('https:' + el[0]['src'])
                item['content_html'] += utils.add_image(img_src)
        if ld_json:
            item['content_html'] += utils.add_stars(ld_json[0]['aggregateRating']['ratingValue'])
        if soup.select('div.recipe-body div.o-RecipeInfo'):
            item['content_html'] += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap;">'
            for el in soup.select('div.recipe-body div.o-RecipeInfo > ul'):
                item['content_html'] += '<div style="flex:1; padding:8px; border:1px solid light-dark(#ccc, #333);">'
                for li in el.find_all('li'):
                    item['content_html'] += '<div>'
                    it = li.find(class_='o-RecipeInfo__a-Headline')
                    if it:
                        item['content_html'] += it.get_text().strip()
                    it = li.find(class_='o-RecipeInfo__a-Description')
                    if it:
                        item['content_html'] += ' <b>' + it.get_text().strip() + '</b>'
                    it = li.find(class_='o-RecipeInfo__a-Note')
                    if it:
                        item['content_html'] += ' <small>' + it.get_text().strip() + '</small>'
                    item['content_html'] += '</div>'
                item['content_html'] += '</div>'
            item['content_html'] += '</div>'
        if soup.find(class_='o-Ingredients'):
            item['content_html'] += '<h3>Ingredients:</h3>'
            ul = False
            for el in soup.find(class_='o-Ingredients__m-Body').children:
                if isinstance(el, str):
                    continue
                if 'o-Ingredients__a-Ingredient--SelectAll' in el['class']:
                    continue
                elif 'o-Ingredients__a-Ingredient' in el['class']:
                    if not ul:
                        item['content_html'] += '<ul>'
                        ul = True
                    it = el.find('input')
                    if it:
                        item['content_html'] += '<li>' + it['value'] + '</li>'
                    else:
                        it = el.find('span', class_='o-Ingredients__a-Ingredient--CheckboxLabel')
                        if it:
                            item['content_html'] += '<li>' + it.get_text().strip() + '</li>'
                elif 'o-Ingredients__a-SubHeadline' in el['class']:
                    if ul:
                        item['content_html'] += '</ul>'
                        ul = False
                    item['content_html'] += '<div style="font-weight:bold;">' + el.get_text().strip() + '</div>'
            item['content_html'] += '</ul>'
        if soup.find(class_='o-Method'):
            item['content_html'] += '<h3>Directions:</h3><ol>'
            for el in soup.find_all('li', class_='o-Method__m-Step'):
                el.attrs = {}
                item['content_html'] += str(el)
            item['content_html'] += '</ol>'
        el = soup.find('template', id='nutrition-content')
        if el:
            item['content_html'] += '<h3>Nutrition Info:</h3><table style="margin-left:1em; border-collapse:collapse;">'
            for i, dt in enumerate(el.find_all('dt')):
                if i == 0:
                    item['content_html'] += '<tr style="border-top:1px solid light-dark(#ccc, #333); border-bottom:1px solid light-dark(#ccc, #333);">'
                else:
                    item['content_html'] += '<tr style="border-bottom:1px solid light-dark(#ccc, #333);">'
                if 'm-NutritionTable__a-Headline--Primary' in dt['class']:
                    item['content_html'] += '<th style="text-align:left; padding:8px;">' + dt.decode_contents().strip() + '</th>'
                else:
                    item['content_html'] += '<td style="padding:8px;">' + dt.decode_contents().strip() + '</td>'
                dd = dt.find_next_sibling('dd')
                if dd:
                    if 'm-NutritionTable__a-Description--Primary' in dd['class']:
                        item['content_html'] += '<th style="text-align:left; padding:8px;">' + dd.decode_contents().strip() + '</th>'
                    else:
                        item['content_html'] += '<td style="padding:8px;">' + dd.decode_contents().strip() + '</td>'
                item['content_html'] += '</tr>'
            item['content_html'] += '</table>'
        return item

    body = soup.find(class_='article-body')
    if body:
        for el in body.find_all(text=lambda text: isinstance(text, Comment)):
            el.extract()

        for el in body.find_all('div', attrs={"data-slot-type": "ad_block_content_after_component"}):
            el.decompose()

        for el in body.find_all('section', class_='o-CustomRTE'):
            el.unwrap()

        for el in body.find_all('section', class_=['o-EditorialPromo', 'o-JukeBox']):
            el.decompose()

        for el in body.find_all('link', attrs={"type": "text/css"}):
            el.decompose()

        for el in body.find_all(class_='o-ImageEmbed'):
            new_html = ''
            gallery_images = []
            if el.find(class_='slideshow-wrapper'):
                slides = el.find_all(class_='slide')
                if len(slides) > 1:
                    new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for i, slide in enumerate(slides):
                    it = slide.find('a', class_='rsImg')
                    if it:
                        img_src = 'https:' + resize_image(it['href'])
                        thumb = 'https:' + resize_image(it['href'], 'thumb')
                        captions = []
                        it = slide.find(class_='o-Attribution')
                        if it and it.get_text().strip():
                            captions.append(it.decode_contents().strip())
                        it = slide.find(class_='photo-copyright')
                        if it and it.get_text().strip():
                            captions.append(it.decode_contents().strip())
                            it.decompose()
                        it = slide.find(class_='photo-caption')
                        if it and it.get_text().strip():
                            captions.insert(0, it.decode_contents().strip())
                        caption = ' | '.join(captions)
                        if len(slides) > 1:
                            new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                            gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                        else:
                            new_html += utils.add_image(img_src, caption)
                if len(slides) > 1:
                    new_html += '</div>'
                    gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                    new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + new_html
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled o-ImageEmbed in ' + item['url'])

        for el in body.find_all(class_='o-ShoppingEmbed'):
            new_html = ''
            for product in el.find_all(class_='m-ProductsList__m-Product'):
                it = product.find(class_='m-Product__m-MediaWrap')
                if it:
                    if it.img:
                        img_src = 'https:' + resize_image(it.img['data-src'])
                        if it.a:
                            link = it.a['href']
                        else:
                            link = ''
                        new_html += utils.add_image(img_src, '', link=link)
                it = product.find(class_='m-Product__a-Headline')
                if it:
                    it.attrs = {}
                    it.find('span', class_='m-Product__a-HeadlineText').unwrap()
                    new_html += str(it)
                it = el.find(class_='m-Product__m-PriceWrap')
                if it:
                    new_html += '<div><small><b>{}</b> | {}</small></div>'.format(it.find(class_='m-Product__a-Price').get_text().strip(), it.find(class_='m-Product__a-Brand').get_text().strip())
                for link in product.find_all('a', class_='m-Product__m-Buy'):
                    new_html += utils.add_button(link['href'], link.get_text().strip())
                if product.find(class_='m-Product__ProsConsWrap'):
                    new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                    pros = product.find(class_='m-Product__ProsConsWrap-Pros')
                    if pros:
                        new_html += '<div style="flex:1; min-width:360px;">'
                        it = pros.find(class_='m-Product__ProsConsWrap-ProsText')
                        if it:
                            new_html += '<div style="font-weight:bold;">' + it.get_text().strip() + '</div>'
                        new_html += '<ul>'
                        for it in pros.find_all(class_='m-Product__ProsConsList-ItemText'):
                            new_html += '<li>' + it.decode_contents().strip() + '</li>'
                        new_html += '</ul></div>'
                    cons = product.find(class_='m-Product__ProsConsWrap-Cons')
                    if cons:
                        new_html += '<div style="flex:1; min-width:360px;">'
                        it = cons.find(class_='m-Product__ProsConsWrap-ConsText')
                        if it:
                            new_html += '<div style="font-weight:bold;">' + it.get_text().strip() + '</div>'
                        new_html += '<ul>'
                        for it in cons.find_all(class_='m-Product__ProsConsList-ItemText'):
                            new_html += '<li>' + it.decode_contents().strip() + '</li>'
                        new_html += '</ul></div>'
                    new_html += '</div>'
                it = product.find(class_='m-Product__a-Description')
                if it:
                    new_html += it.decode_contents()
                if product.find('ol', class_='m-Product__ProductSpecifications-List'):
                    new_html += '<table style="width:100%; border-collapse:collapse;">'
                    for i, li in enumerate(product.select('ol.m-Product__ProductSpecifications-List > li.m-Product__ProductSpecifications-ListItem')):
                        if i == 0:
                            new_html += '<tr style="border-top:1px solid light-dark(#ccc, #333); border-bottom:1px solid light-dark(#ccc, #333);">'
                        else:
                            new_html += '<tr style="border-bottom:1px solid light-dark(#ccc, #333);">'
                        it = li.find(class_='m-Product__ProductSpecifications-ListItem-Name')
                        new_html += '<td style="padding:8px;"><b>' + it.get_text().strip() + '</b></td>'
                        it = li.find(class_='m-Product__ProductSpecifications-ListItem-Value')
                        new_html += '<td style="padding:8px;">' + it.get_text().strip() + '</td>'
                        new_html += '</tr>'
                    new_html += '</table>'
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled o-ShoppingEmbed in ' + item['url'])

        for el in body.find_all(class_='o-ProductRoundup'):
            new_html = ''
            it = el.find(class_='o-ProductRoundup--heading')
            if it:
                it.attrs = {}
                new_html += str(it)
            for product in el.find_all(class_='o-ProductRoundup--item'):
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                it = product.find('a', class_='o-ProductRoundup--linkimage')
                if it:
                    if it.img:
                        new_html += '<div style="flex:1; min-width:128px; max-width:160px;"><a href="https:{}" target="_blank"><img src="{}" style="width:100%;"></a></div>'.format(it['href'], it.img['src'])
                new_html += '<div style="flex:2; min-width:256px;">'
                it = product.select('div.o-ProductRoundup--description > p.o-ProductRoundup--label')
                if it:
                    new_html += '<div style="text-transfor:uppercase; color:red; font-weight:bold;">' + it[0].get_text().strip() + '</div>'
                it = product.select('div.o-ProductRoundup--description > a.o-ProductRoundup--title')
                if it:
                    new_html += '<div><a href="{}">{}</a></div>'.format(it[0]['href'], it[0].get_text().strip())
                # TODO: div.o-ProductRoundup--description > div.o-ProductRoundup--details
                it = product.find('a', class_='o-ProductRoundup--price')
                if it:
                    new_html += '<p><a href="{}">{}</a></p>'.format(it['href'], it.get_text().strip())
                new_html += '</div></div><div>&nbsp;</div>'
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled o-ProductRoundup in ' + item['url'])

        for el in body.find_all('section', class_='o-StepByStepEmbed'):
            new_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            gallery_images = []
            for i, slide in enumerate(el.find_all(class_='m-Carousel__m-Slide')):
                it = slide.find(class_='m-MediaBlock__a-Image')
                if it:
                    img_src = 'https:' + resize_image(it['data-src'], 'orig')
                    thumb = 'https:' + resize_image(it['data-src'], 'thumb')
                    it = slide.find(class_='m-MediaBlock__a-Credit')
                    if it:
                        caption = it.decode_contents().strip()
                    else:
                        caption = ''
                    new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                    gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
            if i % 2 == 0:
                new_html += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
            new_html += '</div><div>&nbsp;</div>'
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + new_html
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled o-StepByStepEmbed in ' + item['url'])

        for el in body.find_all('span', attrs={"data-contrast": True}):
            el.unwrap()

        item['content_html'] += re.sub(r'<span>\s*</span>', '', body.decode_contents())
        item['content_html'] = re.sub(r'<p>\s*</p>', '', item['content_html'])
    return item