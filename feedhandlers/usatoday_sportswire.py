import json, re
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)
    slug = paths[-1].split('.')[0]
    if split_url.path.startswith('/lists/'):
        post_url = '{}://{}/wp-json/wp/v2/listicle?slug={}'.format(split_url.scheme, split_url.netloc, slug)
    elif split_url.path.startswith('/gallery/'):
        post_url = '{}://{}/wp-json/wp/v2/fishburn_gallery?slug={}'.format(split_url.scheme, split_url.netloc, slug)
    else:
        post_url = '{}://{}/wp-json/wp/v2/posts?slug={}'.format(split_url.scheme, split_url.netloc, slug)
    post = utils.get_url_json(post_url)
    if not post:
        return None
    if save_debug:
        utils.write_file(post, './debug/debug.json')

    # Merge two dicts with |
    sportswire_args = args | site_json['sportswire']['args']

    # Just use embed...we extract the content next
    sportswire_args['embed'] = True
    item = wp_posts.get_post_content(post[0], sportswire_args, site_json['sportswire'], save_debug)
    if not item:
        return None
    if 'embed' in args:
        return item

    page_html = utils.get_url_html(url)
    if not page_html:
        return item
    page_soup = BeautifulSoup(page_html, 'lxml')
    content_html = ''
    contents = utils.get_soup_elements(site_json['sportswire']['content'], page_soup)
    for el in contents:
        content_html += el.decode_contents()

    item['content_html'] = ''
    if '_image' in item:
        item['content_html'] += utils.add_image(item['_image'])

    if split_url.path.startswith('/gallery/'):
        page_soup = BeautifulSoup(content_html, 'html.parser')
        gallery_images = []
        gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for el in page_soup.find_all(class_='vertical-gallery'):
            img = el.select('p.vertical-gallery--image > img')
            if img:
                img_src = utils.clean_url(img[0]['data-lazy-src'])
                thumb = img_src + '?w=800'
                img_src = img_src + '?w=1600'
                it = el.find(class_='vertical-gallery--title')
                if it and it.get_text().strip():
                    desc = '<h4>' + it.get_text().strip() + '</h4>'
                else:
                    desc = ''
                captions = []
                it = el.select('div.vertical-gallery--caption > div.vertical-gallery--caption-hidden')
                if it and it[0].get_text().strip():
                    caption = it[0].get_text().strip()
                else:
                    it = el.select('div.vertical-gallery--caption > div.vertical-gallery--caption-text')
                    if it and it[0].get_text().strip():
                        caption = it[0].get_text().strip()
                    else:
                        caption = ''
                if caption:
                    if desc:
                        desc += '<p>' + caption + '</p>'
                    else:
                        captions.append(caption)
                it = el.find(class_='vertical-gallery--author')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, ' | '.join(captions), link=img_src, desc=desc) + '</div>'
                if desc:
                    gallery_images.append({"src": img_src, "caption": ' | '.join(captions), "desc": desc, "thumb": img_src})
                else:
                    gallery_images.append({"src": img_src, "caption": ' | '.join(captions), "thumb": img_src})
            el.decompose()
        gallery_html += '</div>'
        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
        item['content_html'] += wp_posts.format_content(str(page_soup), item, site_json['sportswire'], None, page_soup)
        item['content_html'] += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html
    elif split_url.path.startswith('/lists/'):
        page_soup = BeautifulSoup(content_html, 'html.parser')
        list_html = ''
        if page_soup.find('div', class_='listicles'):
            for el in page_soup.select('div.listicles > div.listicle'):
                if el.find('h3', class_='listicle-header'):
                    list_html += '<h3>'
                    it = el.select('h3.listicle-header > div.listicle-count')
                    if it and it[0].get_text().strip():
                        list_html += '{}. '.format(it[0].get_text().strip())
                    it = el.select('h3.listicle-header > span.listicle-header-text')
                    if it and it[0].get_text().strip():
                        list_html += it[0].get_text().strip()
                    list_html += '</h3>'
                it = el.select('div.listicle-content > div.wp-caption')
                if it:
                    list_html += wp_posts.add_image(it[0], it[0], base_url, site_json)
                for it in el.select('div.listicle-content > div:has(> p)'):
                    list_html += wp_posts.format_content(it.decode_contents(), item, site_json['sportswire'], None, page_soup)
            page_soup.find('div', class_='listicles').decompose()
        item['content_html'] += wp_posts.format_content(str(page_soup), item, site_json['sportswire'], None, page_soup)
        item['content_html'] += list_html
    else:
        item['content_html'] += wp_posts.format_content(content_html, item, site_json['sportswire'], None, page_soup)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item
