import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


# Future PLC brands: https://www.futureplc.com/our-brands/

def get_img_src(el, img_class=''):
    img_src = ''
    if img_class:
        it = el.find('img', class_=img_class)
    else:
        it = el.find('img')
    if it:
        if it.get('data-srcset'):
            img_src = utils.image_from_srcset(it['data-srcset'], 1000)
        elif it.get('srcset'):
            img_src = utils.image_from_srcset(it['srcset'], 1000)
        elif it.get('data-original-mos'):
            img_src = it['data-original-mos']
        elif it.get('data-pin-media'):
            img_src = it['data-pin-media']
        else:
            img_src = it['src']
    return img_src


def add_image(el, img_class=''):
    captions = []
    it = el.find(class_='caption-text')
    if it and it.get_text().strip():
        captions.append(it.get_text().strip())
    it = el.find(class_='credit')
    if it and it.get_text().strip():
        captions.append(re.sub(r'^\((.*)\)$', r'\1', it.get_text().strip()))
    img_src = get_img_src(el, img_class)
    if not img_src:
        if captions:
            img_src = '{}/image?width=1000&height=560'.format(config.server)
        else:
            return ''
    return utils.add_image(img_src, ' | '.join(captions))


def add_widget(model_name, widget_type, ffte):
    widget_html = ''
    if ffte:
        #widget_url = '{}/widget.php?model_name={}&article_type={}&article_category=retail&language={}&site={}&filter_product_types=deals%2Ccontracts%2Csubscriptions%2Cbroadband&device=mobile&origin=widgets-clientside'.format(ffte['regionUrl'].replace('www.', 'hawk.'), model_name, widget_type, ffte['lang'], ffte['site'].upper())
        widget_url = 'https://search-api.fie.futurecdn.net/widget.php?model_name={}&article_type={}&article_category=retail&language={}&site={}&filter_product_types=deals%2Ccontracts%2Csubscriptions%2Cbroadband&device=mobile&origin=widgets-clientside'.format(model_name.replace('_', '%20'), widget_type, ffte['lang'], ffte['site'].upper())
        widget_json = utils.get_url_json(widget_url)
        utils.write_file(widget_json, './debug/widget.json')
        if widget_json and widget_json['widget']['data'].get('offers'):
            if widget_json['widget']['data']['offers'][0].get('image'):
                img_src = widget_json['widget']['data']['offers'][0]['image']
            elif widget_json['widget']['data']['offers'][0].get('model_image'):
                img_src = widget_json['widget']['data']['offers'][0]['model_image']
            elif widget_json['widget']['data']['offers'][0]['merchant'].get('logo_url'):
                img_src = widget_json['widget']['data']['offers'][0]['merchant']['logo_url']
            else:
                img_src = '{}/image?width=128&height=128'.format(config.server)
            widget_html = '<table><tr><td><img src="{}" style="width:128px;" /></td>'.format(img_src)
            widget_html += '<td><span style="font-size:1.1em; font-weight:bold;">{}</span><ul>'.format(widget_json['widget']['data']['title'])
            for offer in widget_json['widget']['data']['offers']:
                widget_html += '<li>{}{} <a href="{}">{}</a></li>'.format(offer['offer']['currency_symbol'], offer['offer']['price'], utils.get_redirect_url(offer['offer']['link']), offer['offer']['merchant_link_text'])
            widget_html += '</ul></td></tr></table>'
    return widget_html


def get_rating(el, editors_choice):
    n = 0.0
    for star in el.find_all(class_='icon-star'):
        if 'half' in star['class']:
            n = n + 0.5
        else:
            n = n + 1.0
    rating = '<p><strong>'
    if editors_choice:
        rating += '<span style="font-size:1.2em; color:red;">Editors Choice</span><br/>'
    rating += 'Rating: {} out of 5 stars</strong></p>'.format(n)
    return rating


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    soup = BeautifulSoup(page_html, 'lxml')

    ld_json = None
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if ld_json.get('@type') == 'NewsArticle':
            break
        ld_json = None

    ffte = None
    el = soup.find('script', string=re.compile(r'window\.ffte = '))
    if el:
        m = re.search(r'window\.ffte = (.*)', el.string)
        if m:
            ffte = json.loads(m.group(1))

    item = {}
    if ld_json:
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')

        item['id'] = ld_json['url']
        item['url'] = ld_json['url']
        item['title'] = ld_json['headline']

        dt = datetime.fromisoformat(ld_json['datePublished'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(ld_json['dateModified'])
        item['date_modified'] = dt.isoformat()

        item['author'] = {}
        if ld_json.get('author'):
            item['author']['name'] = ld_json['author']['name']
        elif ld_json.get('creator'):
                item['author']['name'] = ld_json['creator']['name']
        elif ld_json.get('publisher'):
                item['author']['name'] = ld_json['publisher']['name']

        if ld_json.get('keywords'):
            item['tags'] = ld_json['keywords'].copy()

        if ld_json.get('image'):
            item['_image'] = ld_json['image']['url']
        elif ld_json.get('thumbnailUrl'):
            item['_image'] = ld_json['thumbnailUrl']

        if ld_json.get('alternativeHeadline'):
            item['summary'] = ld_json['alternativeHeadline']

    if not item.get('id'):
        item['id'] = utils.clean_url(url)
        el = soup.find('link', attrs={"rel": "canonical"})
        if el:
            item['id'] = el['href']
        else:
            item['id'] = utils.clean_url(url)

    if not item.get('url'):
        item['url'] = item['id']

    if not item.get('title'):
        el = soup.find('meta', attrs={"property": "og:title"})
        if el:
            item['title'] = el['content']
        else:
            item['title'] = soup.title.get_text()

    if not item.get('date_published'):
        dt = None
        el = soup.find('meta', attrs={"property": "article:published_time"})
        if el:
            dt = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
        else:
            el = soup.find('meta', attrs={"name": "pub_date"})
            if el:
                dt = datetime.fromisoformat(el['content'])
        if dt:
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

    if not item.get('date_modified'):
        el = soup.find('meta', attrs={"property": "article:modified_time"})
        if el:
            dt = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
            item['date_modified'] = dt.isoformat()

    if not item.get('author'):
        el = soup.find('meta', attrs={"name": "parsely-author"})
        if el:
            item['author'] = {"name": el['content']}
        else:
            el = soup.find(class_='author-byline__author-name')
            if el:
                item['author'] = {"name": el.get_text()}

    if not item.get('_image'):
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']

    if not item.get('tags'):
        el = soup.find('meta', attrs={"name": "parsely-tags"})
        if el:
            item['tags'] = el['content'].replace('Category: ', '').split(',')

    if not item.get('summary'):
        el = soup.find('meta', attrs={"property": "og:description"})
        if el:
            item['summary'] = el['content']
        else:
            el = soup.find('meta', attrs={"name": "description"})
            if el:
                item['summary'] = el['content']

    item['content_html'] = ''
    if item.get('summary'):
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    el = soup.find(class_=['hero-image-wrapper', 'image--hero'])
    if el:
        new_html = add_image(el)
        if new_html:
            item['content_html'] += new_html
        else:
            logger.warning('unhandled hero-image in ' + item['url'])
    else:
        el = soup.find(class_='header-container')
        if el:
            new_html = add_image(el, 'hero-image')
            if new_html:
                item['content_html'] += new_html
            else:
                logger.warning('unhandled header-container image in ' + item['url'])

    el = soup.find(class_='pretty-verdict')
    if el:
        it = el.find(class_='pretty-verdict__heading-container')
        if it:
            rating = it.find(class_='rating')
            if rating:
                new_html = get_rating(rating, soup.find(class_='sprite-award-editors-choice'))
                rating.insert_after(BeautifulSoup(new_html, 'html.parser'))
                rating.decompose()
            it.unwrap()
        it = el.find(class_='pretty-verdict__verdict')
        if it:
            it.unwrap()
        for it in el.find_all(class_=['pretty-verdict__pros', 'pretty-verdict__cons']):
            if it.h4:
                it.h4.attrs = {}
            for li in it.find_all('li'):
                new_html = '<li>{}</li>'.format(re.sub(r'^(\+|-)', '', li.get_text().strip()))
                li.insert_after(BeautifulSoup(new_html, 'html.parser'))
                li.decompose()
            it.unwrap()
        for it in el.find_all('aside'):
            new_html = ''
            if it.find(class_='hawk-merchant-link-widget-main-container'):
                elm = it.find(class_='hawk-title-merchantlink-title-responsive')
                if elm:
                    new_html += '<h4>{}</h4>'.format(elm.get_text())
                new_html += '<ul>'
                for elm in it.find_all(class_='hawk-merchant-link-widget-item-wrapper'):
                    link = elm.find(class_='hawk-affiliate-link-merchantlink-transparent-label')
                    new_html += '<li><a href="{}">'.format(utils.get_redirect_url(link['href']))
                    price = elm.find(class_='hawk-display-price-price')
                    if price:
                        new_html += price.get_text() + ' '
                    new_html += '{}</a></li>'.format(link.get_text())
                it.insert_after(BeautifulSoup(new_html, 'html.parser'))
            elif 'widget' in it.get('data-name'):
                new_html = add_widget(it['data-model-name'], it['data-widget-type'], ffte)
                if new_html:
                    it.insert_after(BeautifulSoup(new_html, 'html.parser'))
            else:
                logger.warning('unhandled pretty-verdict aside in ' + item['url'])
            it.decompose()

        item['content_html'] += el.decode_contents()

        elm =  el.find_next_sibling()
        if elm and elm.get('class') and 'how-we-test' in elm['class']:
            new_html = '<p>'
            it = elm.find(class_='how-we-test__title')
            if it:
                new_html += '<strong>{}</strong>&nbsp;&#9989;&nbsp;'.format(it.get_text().strip())
            it = elm.find(attrs={"data-test": "how-we-test__description"})
            if it:
                new_html += it.decode_contents()
            new_html += '</p>'
            item['content_html'] += new_html

        item['content_html'] += '<hr/>'

    body = soup.find(id='article-body')
    if body:
        for el in body.find_all(class_=['ad-unit', 'newsletter-signup', 'remixd-audioplayer__container', 'table__instruction', 'van_vid_carousel']):
            el.decompose()

        for el in body.find_all('aside'):
            el.decompose()

        for el in body.find_all('script', id=re.compile('vanilla-slice-person-\d+-hydrate')):
            el.decompose()
        for el in body.find_all(id=re.compile(r'slice-container-person-\d+')):
            el.decompose()

        for el in body.find_all(class_='table-wrapper'):
            el.unwrap()
        for el in body.find_all(class_='table__container'):
            el.unwrap()
        for el in body.find_all('table'):
            el.attrs = {}

        for el in body.find_all(re.compile(r'^h\d')):
            el.attrs = {}

        for el in body.find_all(class_='sr-only'):
            el.decompose()

        for el in body.find_all('figure', class_=False):
            if el.blockquote:
                author = ''
                if el.figcaption:
                    it = el.find('cite')
                    if it:
                        author = it.get_text().strip()
                    el.figcaption.decompose()
                new_html = utils.add_pullquote(el.blockquote.decode_contents(), author)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in body.find_all('figure', class_='van-image-figure'):
            new_html = add_image(el)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                if el.parent and el.parent.name == 'a':
                    el.parent.insert_after(new_el)
                    el.parent.decompose()
                else:
                    el.insert_after(new_el)
                    el.decompose()
            else:
                logger.warning('unhandled van-image-figure in ' + item['url'])

        for el in body.find_all(class_='imageGallery-wrapper'):
            new_html = ''
            m = re.search(r'-(imageGallery-\d+)', el['id'])
            if m:
                it = body.find('script', id=re.compile(r'-{}-hydrate'.format(m.group(1))))
                if it:
                    m = re.search('var data = (\{.*?\});\n', it.string)
                    if m:
                        gallery_json = json.loads(m.group(1))
                        if save_debug:
                            utils.write_file(gallery_json, './debug/gallery.json')
                        for slide in gallery_json['galleryData']:
                            if slide['image'].get('credit'):
                                caption = slide['image']['credit']['text']
                                for key, val in slide['image']['credit'].items():
                                    if key != 'text':
                                        caption = caption.replace('{{{}}}'.format(key), val)
                            else:
                                caption = ''
                            new_html += utils.add_image(slide['image']['src'], caption)
                    it.decompose()
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled imageGallery-wrapper in ' + item['url'])

        for el in body.find_all(class_='jwplayer__widthsetter'):
            new_html = ''
            it = el.find(class_='future__jwplayer')
            if it:
                m = re.search(r'futr_botr_([^_]+)_', it['id'])
                if m:
                    new_html = utils.add_embed('https://cdn.jwplayer.com/v2/media/' + m.group(1))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled jwplayer__widthsetter in ' + item['url'])

        for el in body.find_all(class_='youtube-video'):
            new_html = ''
            it = el.find('iframe')
            if it:
                if it.get('data-lazy-src'):
                    new_html = utils.add_embed(it['data-lazy-src'])
                elif it.get('src'):
                    new_html = utils.add_embed(it['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled youtube-video in ' + item['url'])

        for el in body.find_all(class_='see-more'):
            new_html = ''
            if el.find(class_='twitter-tweet'):
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled see-more section in ' + item['url'])

        for el in body.find_all(class_='instagram-embed'):
            new_html = ''
            it = el.find('a', attrs={"data-url": True})
            if it:
                new_html = utils.add_embed(it['data-url'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled instagram-embed in ' + item['url'])

        for el in body.find_all(class_='soundcloud-embed'):
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['data-lazy-src'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled soundcloud-embed in ' + item['url'])

        for el in body.find_all(class_='hawk-nest'):
            if el.name == 'aside':
                el.decompose()
            elif el.get('data-render-type') == 'editorial':
                new_html = '<table><tr>'
                if el.get('data-image'):
                    new_html += '<td><img src="{}" style="width:128px;" /></td>'.format(el['data-image'])
                else:
                    new_html += '<td style="width:18px;">&nbsp;</td>'
                if el.get('data-widget-introduction'):
                    new_html += '<td>{}</td>'.format(el['data-widget-introduction'])
                new_html += '</tr></table>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled hawk-nest in ' + item['url'])

        for el in body.find_all(class_='featured_product_block'):
            if 'featured_block_horizontal' in el['class']:
                new_html = '<table><tr><td><img src="{}" style="width:128px;" /></td><td>'.format(get_img_src(el))
            else:
                new_html = add_image(el)
            it = el.find(class_='featured__title')
            if it:
                if el.a:
                    new_html += '<h3><a href="{}">{}</a></h3>'.format(el.a['href'], it.get_text())
                else:
                    new_html += '<h3>{}</h3>'.format(it.get_text())
            if el.find(class_='stars__reviews'):
                new_html += get_rating(el, soup.find(class_='sprite-award-editors-choice'))
            it = el.find(class_='subtitle__description')
            if it:
                new_html += it.decode_contents()
            if 'featured_block_horizontal' in el['class']:
                new_html += '</td></tr></table>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='product'):
            it = el.find(class_='title-and-rating')
            if it:
                it.unwrap()
            it = el.find(class_='rating')
            if it:
                new_el = BeautifulSoup(get_rating(it, None), 'html.parser')
                it.insert_after(new_el)
                it.decompose()
            it = el.find(class_='subtitle')
            if it:
                it.name = 'h3'
                it.attrs = {}
            it = el.find(class_='spec')
            if it:
                elm = it.find(class_='product-summary__container')
                if elm:
                    new_html = '<ul>'
                    for entry in elm.find_all(class_='spec__entry'):
                        new_html += '<li>{}&nbsp;{}</li>'.format(entry.find(class_='spec__name').get_text(), entry.find(class_='spec_value').get_text())
                    new_html += '</ul>'
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    elm.insert_after(new_el)
                    elm.decompose()
                it.unwrap()
            it = el.find(class_='pros')
            if it:
                elm = it.find(class_='product-summary__container')
                if elm:
                    new_html = '<ul>'
                    for entry in el.find_all(class_='cons__entry'):
                        new_html += '<li>{}</li>'.format(entry.get_text().strip())
                    new_html += '</ul>'
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    elm.insert_after(new_el)
                    elm.decompose()
                it.unwrap()
            it = el.find(class_='cons')
            if it:
                elm = it.find(class_='product-summary__container')
                if elm:
                    new_html = '<ul>'
                    for entry in el.find_all(class_='cons__entry'):
                        new_html += '<li>{}</li>'.format(entry.get_text().strip())
                    new_html += '</ul>'
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    elm.insert_after(new_el)
                    elm.decompose()
                it.unwrap()
            for it in el.find_all(class_='hawk-wrapper'):
                if it.get_text().strip() == '':
                    it.decompose()
                else:
                    logger.warning('unhandled product hawk-wrapper in ' + item['url'])
            el.unwrap()

        for el in body.find_all(class_='howWeTest-wrapper'):
            new_html = '<p>'
            it = el.find(class_='how-we-test__title')
            if it:
                new_html += '<strong>{}</strong>&nbsp;&#9989;&nbsp;'.format(it.get_text().strip())
            it = el.find(attrs={"data-test": "how-we-test__description"})
            if it:
                new_html += it.decode_contents()
            new_html += '</p>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='fancy-box'):
            it = el.find(class_='fancy_box-title')
            if it:
                if re.search(r'read more|related stories', it.get_text(), flags=re.I):
                    el.decompose()
            else:
                logger.warning('unhandled fancy-box in ' + item['url'])

        for el in body.find_all('iframe'):
            if el.get('src'):
                new_html = utils.add_embed(el['src'])
            elif el.get('data-lazy-src'):
                new_html = utils.add_embed(el['data-lazy-src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        item['content_html'] += body.decode_contents()

        if el in body.find_all(class_='product-container'):
            # several featured_product_block's can be in a product container
            el.unwrap()

    item['content_html'] = re.sub(r'</(div|figure|table)>\s*<(div|figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/feeds/' in args['url'] or 'rss' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    page_html = utils.get_url_html(args['url'])
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')

    n = 0
    feed_items = []
    for el in soup.find_all(class_='listingResult'):
        it = el.find('a', class_='article-link')
        if it:
            if save_debug:
                logger.debug('getting content for ' + it['href'])
            item = get_content(it['href'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
    feed = utils.init_jsonfeed(args)
    feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed