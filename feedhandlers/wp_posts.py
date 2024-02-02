import av, bs4, html, json, math, random, re
import pytz
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, site_json, width=1000, height=800):
    #print(img_src)
    # if site_json and site_json.get('resize_image'):
    #     return utils.clean_url(img_src) +
    split_url = urlsplit(img_src)
    query = parse_qs(split_url.query)
    img_path = '{}://{}'.format(split_url.scheme, split_url.netloc)
    if site_json and site_json.get('img_path'):
        img_src = img_src.replace(img_path, site_json['img_path'])
        img_path = site_json['img_path']
    if query.get('url'):
        #print(query)
        return img_src
    if query.get('w') or query.get('h') or query.get('fit'):
        return '{}{}?w={}&ssl=1'.format(img_path, split_url.path, width)
    if query.get('width') or query.get('height'):
        return '{}{}?width={}'.format(img_path, split_url.path, width)
    if query.get('resize') and not query.get('crop'):
        m = re.search(r'(\d+),(\d+)', query['resize'][0])
        if m:
            w = int(m.group(1))
            h = int(m.group(2))
            height = math.floor(h * width / w)
            return '{}{}?resize={},{}'.format(img_path, split_url.path, width, height)
    m = re.search(r'GettyImages-\d+(-\d+x\d+[^\.]*)', split_url.path)
    if m:
        return img_src.replace(m.group(1), '')
    return img_src


def add_image(el, el_parent, base_url, site_json, caption=True, decompose=True, gallery=False, n=0):
    # print(el)
    if el.name == None:
        return

    if el.name == 'img':
        img = el
    else:
        img = el.find('img')
        if not img:
            img = el.find('amp-img')
            if not img:
                img = el.find('source')
    if not img:
        logger.warning('image block without img')
        # print(el)
        return

    it = img.find_parent('a')
    if it and it.get('href'):
        link = it['href']
    else:
        link = ''

    if not el_parent:
        el_parent = el
        for it in reversed(el.find_parents()):
            # print('Parent: ' + it.name)
            if it.name == '[document]':
                break
            elif it.name == 'table' or it.name == 'tbody' or it.name == 'tr' or it.name == 'td':
                continue
            elif it.name == 'p':
                has_str = False
                for c in it.contents:
                    if isinstance(c, bs4.element.NavigableString) or (isinstance(c, bs4.element.Tag) and c.name in ['b', 'em', 'i', 'strong']):
                        has_str = True
                if not has_str:
                    el_parent = it
                    break
            elif not it.find('p'):
                el_parent = it
                break
        # if el.parent and el.parent.name == 'a' and el.parent.get('href'):
        #     el_parent = el.parent
        # if el_parent.parent and (el_parent.parent.name == 'center' or el_parent.parent.name == 'figure'):
        #     el_parent = el_parent.parent
        # if el_parent.parent and re.search(r'^(div|h\d|p)$', el_parent.parent.name):
        #     el_parent = el_parent.parent

    # print(el_parent['class'])

    images = []
    for src in el_parent.find_all('source'):
        if src.get('srcset') and src.get('media'):
            if 'min-width' in src['media']:
                m = re.search(r'(\d+)px', src['media'])
                if m:
                    image = {}
                    image['src'] = src['srcset']
                    image['width'] = int(m.group(1))
                    images.append(image)
    if images:
        image = utils.closest_dict(images, 'width', 1000)
        img_src = image['src']
    else:
        if link and img.get('class') and 'attachment-thumbnail' in img['class']:
            img_src = link
            link = ''
        elif link and re.search(r'\.jpg|\.jpeg|\.png', link):
            # likely the full-size image
            img_src = link
        elif img.get('data-orig-file'):
            img_src = img['data-orig-file']
        elif img.get('data-lazy-srcset') and not img['data-lazy-srcset'].startswith('data:image/gif;base64'):
            img_src = utils.image_from_srcset(img['data-lazy-srcset'], 1000)
        elif img.get('data-lazy-load-srcset') and not img['data-lazy-load-srcset'].startswith('data:image/gif;base64'):
            img_src = utils.image_from_srcset(img['data-lazy-load-srcset'], 1000)
        elif img.get('data-srcset') and not img['data-srcset'].startswith('data:image/gif;base64'):
            img_src = utils.image_from_srcset(img['data-srcset'], 1000)
        elif img.get('srcset') and not img['srcset'].startswith('data:image/gif;base64'):
            img_src = utils.image_from_srcset(img['srcset'], 1000)
        elif img.get('data-lazy-src') and not img['data-lazy-src'].startswith('data:image/gif;base64'):
            img_src = img['data-lazy-src']
        elif img.get('data-lazy-load-src') and not img['data-lazy-load-src'].startswith('data:image/gif;base64'):
            img_src = img['data-lazy-load-src']
        elif img.get('data-dt-lazy-src') and not img['data-dt-lazy-src'].startswith('data:image/gif;base64'):
            img_src = img['data-dt-lazy-src']
        elif img.get('data-src') and not img['data-src'].startswith('data:image/gif;base64'):
            img_src = img['data-src']
        else:
            img_src = img['src']

    if img_src.startswith('//'):
        img_src = 'https:' + img_src
    elif img_src.startswith('/'):
        img_src = base_url + img_src

    if re.search(r'abyssalchronicles.*thumb_', img_src):
        img_src = img_src.replace('thumb_', 'normal_')

    captions = []
    if el_parent.get('class') and 'multiple-images' in el_parent['class']:
        cap = '({})'.format(n)
        if caption:
            it = el_parent.find(class_='multiple-images__caption')
            if it:
                captions.append(cap + '<br/><br/>' + it.decode_contents())
        else:
            captions.append(cap)
    if caption:
        if el.get('class') and 'bp-embedded-image' in el['class']:
            for it in el.find_all('em'):
                captions.append(it.get_text())
        else:
            if el_parent and el_parent.get('class') and 'photo-layout' in el_parent['class']:
                elm = el_parent
            elif gallery:
                elm = el
            else:
                elm = el_parent

            credit = ''
            it = elm.find('cite')
            if it and it.get_text().strip():
                credit = it.get_text().strip()
            it = elm.find(class_='credit')
            if it and it.get_text().strip():
                credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='imageCredit')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_=re.compile(r'image-attribution|image-credit|photo-credit|credits-text|image_source'))
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='slide-caption')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='slide-credit')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='attribution')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='source')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='visual-by')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='author-name')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if not credit:
                it = elm.find(class_='article-media__photographer')
                if it and it.get_text().strip():
                    credit = it.get_text().strip()
            if it:
                it.decompose()

            it = elm.find(class_='caption')
            if it and it.get_text().strip():
                captions.insert(0, it.get_text().strip())
            if not captions:
                it = elm.find(class_=re.compile(r'wp-block-media-text__content'))
                if it and it.get_text().strip():
                    captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', it.decode_contents().strip()))
            if not captions:
                it = elm.find(class_=re.compile(r'caption-text|image-caption|photo-layout__caption|article-media__featured-caption|m-article__hero-caption|media-caption|rslides_caption|atr-caption'))
                if it and it.get_text().strip():
                    captions.append(it.get_text())
            if not captions:
                it = elm.find(class_=re.compile(r'text'))
                if it and it.get_text().strip():
                    captions.append(it.get_text())
            if not captions:
                it = elm.find(class_='undark-caption')
                if it and it.get_text().strip():
                    captions.append(it.decode_contents().replace('<p>', '').replace('</p>', ' ').strip())
            if not captions:
                it = elm.find(class_='box-text-inner')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
            if not captions:
                it = elm.find(class_='singleImageCaption')
                if it and it.get_text().strip():
                    i = it.find('i', class_='fas')
                    if i:
                        i.decompose()
                    captions.append(it.decode_contents())
            if not captions:
                for it in elm.find_all(class_=['elementor-image-box-title', 'elementor-image-box-description']):
                    captions.append(it.decode_contents())
            if not captions:
                it = elm.find('figcaption')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())

            if credit:
                captions.append(credit)

            if not captions:
                if img.get('data-image-caption'):
                    captions.append(img['data-image-caption'])
                elif img.get('data-image-title') and not re.search(r'\w(_|-)\w||\w\d+$', img['data-image-title']):
                    captions.append(img['data-image-title'])

            if not captions:
                it = el.find_next_sibling()
                if it and it.get('class') and 'caption-hold' in it['class']:
                    captions.append(it.get_text())
                    it.decompose()

    desc = ''
    if el.find(class_='picture-desc'):
        it = el.find(class_='gallery-heading')
        if it and it.get_text().strip():
            desc += '<h3>{}</h3>'.format(it.get_text().strip())
        it = el.find(class_='gallery-content')
        if it and it.get_text().strip():
            it.attrs = {}
            it.name = 'p'
            desc += str(it)
    elif el.find(class_='gallery-item__caption'):
        it = el.find(class_='gallery-item__caption')
        desc = it.decode_contents()

    if not (el.get('class') and 'bannerad' in el['class']):
        new_html = utils.add_image(resize_image(img_src, site_json), ' | '.join(captions), link=link, desc=desc)
        new_el = BeautifulSoup(new_html, 'html.parser')
        try:
            el_parent.insert_before(new_el)
        except:
            el_parent.append(new_el)

    if decompose:
        if len(el_parent.find_all('img')) > 1:
            el.decompose()
        else:
            el_parent.decompose()
    return new_html


def render_content(content, url):
    content_html = ''
    for block in content:
        if isinstance(block, str):
            content_html += block

        elif isinstance(block, dict):
            if block.get('tag'):
                if block['tag'] == 'a':
                    content_html += '<a href="{}">{}</a>'.format(block['attributes']['href'], render_content(block['content'], url))
                elif block['tag'] == 'caption':
                    image = next((it for it in block['content'] if it['tag'] == 'img'), None)
                    if image:
                        captions = []
                        caption = next((it for it in block['content'] if isinstance(it, dict) and it['tag'] == 'figcaption'), None)
                        if caption and caption.get('content'):
                            captions.append(render_content(caption['content'], url))
                        caption = next((it for it in block['content'] if isinstance(it, dict) and it['tag'] == 'figcredit'), None)
                        if caption and caption.get('content'):
                            captions.append(render_content(caption['content'], url))
                        content_html += utils.add_image(image['attributes']['src'], ' | '.join(captions))
                    else:
                        logger.warning('unhandled caption tag')
                elif block['tag'] == 'video':
                    if 'time.com' in url and block['attributes'].get('videoid'):
                        content_html += utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(block['attributes']['videoid']))
                else:
                    #print(block['tag'])
                    content_html += '<{0}>{1}</{0}>'.format(block['tag'],render_content(block['content'], url))
            else:
                logger.warning('unhandled dict block without tag')

        else:
            logger.warning('unhandled block type {}'.format(type(block)))

    return content_html


def get_authors(wp_post, yoast_json, page_soup, item, args, site_json, meta_json=None, ld_article=None, ld_people=None, oembed_json=None):
    authors = []
    if site_json.get('author'):
        if not page_soup:
            page_html = utils.get_url_html(item['url'])
            if page_html:
                page_soup = BeautifulSoup(page_html, 'lxml')
        if page_soup:
            for el in utils.get_soup_elements(site_json['author'], page_soup):
                if el.name == 'meta':
                    if el.get('data-separator'):
                        authors = [it.strip() for it in el['content'].split(el['data-separator'])]
                    else:
                        authors.append(el['content'])
                elif el.name == 'a':
                    authors.append(el.get_text())
                else:
                    for it in el.find_all('a', href=re.compile(r'author|correspondents|staff')):
                        authors.append(it.get_text())
                if not authors and el.get_text().strip():
                    authors.append(re.sub(r'^By ', '', el.get_text().strip(), flags=re.I))
                if authors:
                    break
    if authors:
        return authors

    if yoast_json and yoast_json.get('twitter_misc') and yoast_json['twitter_misc'].get('Written by'):
        authors.append(yoast_json['twitter_misc']['Written by'])
        return authors

    if wp_post:
        if wp_post.get('yoast_head_json') and wp_post['yoast_head_json'].get('twitter_misc') and wp_post['yoast_head_json']['twitter_misc'].get('Written by') and wp_post['yoast_head_json']['twitter_misc']['Written by'].lower() != 'administrator':
            authors.append(wp_post['yoast_head_json']['twitter_misc']['Written by'])
            return authors

        if wp_post.get('rj_fields') and wp_post['rj_fields'].get('_rj_field_byline_author') and wp_post['rj_fields']['_rj_field_byline_author'].get('authors'):
            return wp_post['rj_fields']['_rj_field_byline_author']['authors'].copy()

        if wp_post.get('authors'):
            for it in wp_post['authors']:
                if isinstance(it, dict):
                    if it.get('display_name'):
                        authors.append(it['display_name'])
                    elif it.get('name'):
                        authors.append(it['name'])
            return authors

        if wp_post.get('author') and isinstance(wp_post['author'], dict):
            authors.append(wp_post['author']['name'])
            return authors

        if wp_post.get('author_info'):
            if wp_post['author_info'].get('display_name'):
                authors.append(wp_post['author_info']['display_name'])
                return authors
            elif wp_post['author_info'].get('name'):
                authors.append(wp_post['author_info']['name'])
                return authors

        if wp_post.get('byline'):
            for it in wp_post['byline']:
                if isinstance(it, dict) and it.get('text'):
                    authors.append(it['text'])
            return authors

        if wp_post.get('bylines'):
            for it in wp_post['bylines']:
                if it.get('display_name'):
                    authors.append(it['display_name'])
            return authors

        if wp_post.get('shared_authors'):
            for it in wp_post['shared_authors']:
                authors.append(it['title'])
            return authors

        if wp_post.get('post_meta') and wp_post['post_meta'].get('personOverride'):
            if isinstance(wp_post['post_meta']['personOverride'], list):
                return wp_post['post_meta']['personOverride'].copy()
            elif isinstance(wp_post['post_meta']['personOverride'], str):
                authors.append(wp_post['post_meta']['personOverride'])
                return authors

        if not authors and wp_post.get('meta') and wp_post['meta'].get('byline') and isinstance(wp_post['meta']['byline'], str):
            authors.append(wp_post['meta']['byline'])
            return authors

        if not authors and wp_post.get('metadata') and wp_post['metadata'].get('author'):
            return wp_post['metadata']['author'].copy()

        if wp_post.get('parsely') and wp_post['parsely'].get('meta') and wp_post['parsely']['meta'].get('author'):
            for author in wp_post['parsely']['meta']['author']:
                authors.append(author['name'])
            return authors

        if wp_post.get('parsely') and wp_post['parsely'].get('meta') and wp_post['parsely']['meta'].get('creator'):
            return wp_post['parsely']['meta']['creator'].copy()

        if wp_post.get('parselyMeta') and wp_post['parselyMeta'].get('parsely-author'):
            return wp_post['parselyMeta']['parsely-author'].copy()

        if wp_post.get('_links') and wp_post['_links'].get('ns:byline'):
            for link in wp_post['_links']['ns:byline']:
                if site_json.get('replace_links_path'):
                    link_href = link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
                else:
                    link_href = link['href']
                link_json = utils.get_url_json(link_href)
                if link_json and link_json.get('title'):
                    authors.append(link_json['title']['rendered'])
        if authors:
            return authors

        if wp_post.get('_links') and wp_post['_links'].get('wp:term'):
            for link in wp_post['_links']['wp:term']:
                if link.get('taxonomy') and link['taxonomy'] == 'author':
                    link_json = utils.get_url_json(link['href'])
                    if link_json:
                        for it in link_json:
                            authors.append(it['name'].replace('-', ' ').title())
        if authors:
            return authors

        if wp_post.get('yoast_head_json') and wp_post['yoast_head_json'].get('author'):
            authors.append(wp_post['yoast_head_json']['author'])
            return authors

        if wp_post.get('acf') and wp_post['acf'].get('art_author'):
            for it in wp_post['acf']['art_author']:
                authors.append(it['post_title'])
            return authors

        if wp_post.get('coauthors_byline'):
            authors.append(re.sub(r'By ', '', wp_post['coauthors_byline'], flags=re.I))
            return authors

        if wp_post.get('_links') and wp_post['_links'].get('author'):
            if 'skip_wp_user' not in args:
                for link in wp_post['_links']['author']:
                    if site_json.get('replace_links_path'):
                        link_href = link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1])
                    else:
                        link_href = link['href']
                    link_json = utils.get_url_json(link_href)
                    if link_json and link_json.get('name') and not re.search(r'No Author', link_json['name'], flags=re.I):
                        authors.append(link_json['name'])
                if authors:
                    return authors

            update_sites = False
            wp_item = None
            for i, link in enumerate(wp_post['_links']['author']):
                author = list(filter(None, urlsplit(link['href']).path[1:].split('/')))[-1]
                if site_json.get('authors') and site_json['authors'].get(author):
                    authors.append(site_json['authors'][author])
                elif site_json.get('authors') and site_json['authors'].get('default'):
                    authors.append(site_json['authors']['default'])
                else:
                    if not wp_item:
                        embed_args = args.copy()
                        embed_args['embed'] = True
                        wp_item = wp.get_content(item['url'], embed_args, site_json, False)
                    if wp_item and wp_item.get('author'):
                        wp_authors = re.split(r'(, | and )', wp_item['author']['name'])
                        authors.append(wp_authors[i])
                        if site_json.get('authors'):
                            site_json['authors'][author] = wp_authors[i]
                            logger.debug('adding unknown author {} as {}'.format(author, wp_authors[i]))
                            update_sites = True
                    else:
                        logger.debug('unknown author {} in {}'.format(author, item['url']))
                        authors.append('Unknown author {}'.format(author))
            if update_sites:
                utils.update_sites(item['url'], site_json)
            if authors:
                return authors

        if wp_post.get('_wamu_show'):
            link = next((it for it in wp_post['_links']['wp:term'] if it['taxonomy'] == '_wamu_show'), None)
            if link:
                link_json = utils.get_url_json(link['href'])
                if link_json:
                    for it in link_json:
                        if it.get('name'):
                            authors.append(it['name'])

    # TODO: remove this - it should be caught by ld_people and ld_article
    if yoast_json:
        if yoast_json.get('@graph'):
            for it in yoast_json['@graph']:
                if it.get('@type') and it['@type'] == 'Article' and it.get('author'):
                    if isinstance(it['author'], list):
                        for author in it['author']:
                            if author.get('name'):
                                authors.append(author['name'])
                    elif isinstance(it['author'], dict) and it['author'].get('name'):
                        authors.append(it['author']['name'])
                    elif isinstance(it['author'], str):
                        authors.append(it['author'])
            if not authors:
                for it in yoast_json['@graph']:
                    if it.get('@type') and it['@type'] == 'Person':
                        if it.get('name') and not re.search(r'No Author', it['name'], flags=re.I):
                            authors.append(it['name'])
        if authors:
            return authors

    if ld_people:
        for it in ld_people:
            authors.append(it['name'])
        return authors

    if ld_article:
        if ld_article.get('author'):
            if isinstance(ld_article['author'], dict):
                if ld_article['author'].get('name'):
                    authors.append(ld_article['author']['name'])
            elif isinstance(ld_article['author'], list):
                for it in ld_article['author']:
                    if it.get('name'):
                        authors.append(it['name'])
            if authors:
                return authors

    if meta_json:
        if meta_json.get('author'):
            authors.append(meta_json['author'])
        elif meta_json.get('citation_author'):
            authors.append(meta_json['citation_author'])
        elif meta_json.get('parsely-author'):
            authors.append(meta_json['parsely-author'])
        if authors:
            return authors

    if oembed_json:
        if oembed_json.get('author_name'):
            authors.append(oembed_json['author_name'])
            return authors

    if site_json.get('authors'):
        authors.append(site_json['authors']['default'])
    return authors


def get_post_content(post, args, site_json, page_soup=None, save_debug=False):
    if save_debug:
        utils.write_file(post, './debug/debug.json')

    yoast_json = None
    if post.get('yoast_head_json') and post['yoast_head_json'].get('schema'):
        yoast_json = post['yoast_head_json']['schema']
    elif post.get('yoast_head'):
        soup = BeautifulSoup(post['yoast_head'], 'html.parser')
        el = soup.find('script', class_='yoast-schema-graph')
        if el:
            yoast_json = json.loads(el.string)
    if yoast_json and save_debug:
        utils.write_file(yoast_json, './debug/yoast.json')

    item = {}
    if isinstance(post['guid'], str):
        item['id'] = post['guid']
    else:
        item['id'] = post['guid']['rendered']

    if site_json.get('replace_netloc'):
        item['url'] = post['link'].replace(site_json['replace_netloc'][0], site_json['replace_netloc'][1])
    else:
        item['url'] = post['link']
    split_url = urlsplit(item['url'])
    paths = list(filter(None, split_url.path.split('/')))
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)

    if isinstance(post['title'], str):
        item['title'] = post['title']
    else:
        item['title'] = BeautifulSoup('<p>{}</p>'.format(post['title']['rendered']), 'html.parser').get_text()
    if re.search(r'&[#\w]+;', item['title']):
        item['title'] = html.unescape(item['title'])

    dt = datetime.fromisoformat(post['date_gmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post['modified_gmt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    item['author'] = {}
    authors = get_authors(post, yoast_json, page_soup, item, args, site_json)
    if authors:
        for i in range(len(authors)):
            authors[i] = re.sub(r', (.*)', r' (\1)', authors[i])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        if 'author' in args:
            embed_args = args.copy()
            embed_args['embed'] = True
            wp_item = wp.get_content(item['url'], embed_args, site_json, False)
            if wp_item and wp_item.get('author'):
                item['author']['name'] = wp_item['author']['name']
        else:
            item['author']['name'] = urlsplit(item['url']).netloc

    item['tags'] = []
    if post.get('_links') and 'skip_wp_terms' not in args:
        if 'wp:term' in post['_links']:
            for link in post['_links']['wp:term']:
                if link.get('taxonomy') and link['taxonomy'] != 'author' and link['taxonomy'] != 'channel' and link['taxonomy'] != 'contributor' and link['taxonomy'] != 'site-layouts' and link['taxonomy'] != 'lineup':
                    if site_json.get('replace_links_path'):
                        link_json = utils.get_url_json(link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1]))
                    else:
                        link_json = utils.get_url_json(link['href'])
                    if link_json:
                        for it in link_json:
                            if it.get('name'):
                                item['tags'].append(it['name'])
    if yoast_json:
        keywords = next((it['keywords'] for it in yoast_json['@graph'] if it.get('keywords')), None)
        if keywords:
            if isinstance(keywords, list):
                for tag in keywords:
                    if tag.startswith('category-'):
                        item['tags'] += tag.split('/')[1:]
                    else:
                        item['tags'].append(tag)
            elif isinstance(keywords, str):
                item['tags'] += [tag.strip() for tag in keywords.split(',')]
    if post.get('parsely') and post['parsely'].get('meta') and post['parsely']['meta'].get('keywords'):
        item['tags'] = post['parsely']['meta']['keywords'].copy()
    elif post.get('parselyMeta') and post['parselyMeta'].get('parsely-tags'):
        item['tags'] = post['parselyMeta']['parsely-tags'].split(',')
    elif post.get('terms'):
        if post['terms'].get('category'):
            for it in post['terms']['category']:
                item['tags'].append(it['name'])
        if post['terms'].get('post_tag'):
            for it in post['terms']['post_tag']:
                item['tags'].append(it['name'])
    if item.get('tags'):
        # Remove duplicate tags - case insensitive
        # https://stackoverflow.com/questions/24983172/how-to-eliminate-duplicate-list-entries-in-python-while-preserving-case-sensitiv
        wordset = set(item['tags'])
        item['tags'] = [it for it in wordset if it.istitle() or it.title() not in wordset]
    else:
        del item['tags']

    caption = ''
    if 'skip_wp_media' not in args:
        if post.get('_links') and post['_links'].get('wp:featuredmedia'):
            for link in post['_links']['wp:featuredmedia']:
                if site_json.get('replace_links_path'):
                    link_json = utils.get_url_json(link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1]))
                else:
                    link_json = utils.get_url_json(link['href'])
                if link_json and link_json.get('media_type'):
                    if link_json['media_type'] == 'image':
                        if link_json.get('media_details') and link_json['media_details'].get('sizes'):
                            image = None
                            if link_json['media_details']['sizes'].get('full'):
                                image = link_json['media_details']['sizes']['full']
                            else:
                                # Filter image sizes
                                images = []
                                landscape = []
                                for key, val in link_json['media_details']['sizes'].items():
                                    if any(it in key for it in ['thumb', 'small', 'tiny', 'landscape', 'portrait', 'square', 'logo', 'footer', 'archive', 'column', 'author', 'sponsor', 'hero']):
                                        continue
                                    images.append(val)
                                    if val['width'] >= val['height']:
                                        landscape.append(val)
                                if landscape:
                                    image = utils.closest_dict(landscape, 'width', 1000)
                                elif images:
                                    image = utils.closest_dict(images, 'width', 1000)
                            if image and image.get('source_url'):
                                item['_image'] = image['source_url']
                            elif image and image.get('url'):
                                item['_image'] = image['url']
                        if not item.get('_image'):
                            item['_image'] = link_json['source_url']
                        captions = []
                        if link_json.get('description'):
                            if isinstance(link_json['description'], str):
                                captions.append(link_json['description'])
                            elif link_json['description'].get('rendered'):
                                soup = BeautifulSoup(link_json['description']['rendered'], 'html.parser')
                                if not soup.find('img'):
                                    caption = soup.get_text().strip()
                                    if caption:
                                        if link_json['description']['rendered'].startswith('<p'):
                                            caption = soup.p.decode_contents().strip()
                                        captions.append(caption)
                        if not captions and link_json.get('caption') and link_json['caption'].get('rendered') and isinstance(link_json['caption']['rendered'], str):
                            caption = re.sub(r'<br\s?/?>', '. ', link_json['caption']['rendered'])
                            soup = BeautifulSoup(caption, 'html.parser')
                            for el in soup.find_all('a'):
                                if not el.get_text().strip():
                                    el.decompose()
                            caption = re.sub(r'[\.\s]+$', '', soup.get_text().strip())
                            if caption:
                                if link_json['caption']['rendered'].startswith('<p'):
                                    caption = re.sub(r'[\.\s]+$', '', soup.p.decode_contents().strip())
                                captions.append(caption)
                        if not captions and link_json.get('title'):
                            soup = BeautifulSoup(link_json['title']['rendered'], 'html.parser')
                            caption = soup.get_text().strip()
                            if caption:
                                if link_json['title']['rendered'].startswith('<p'):
                                    caption = soup.p.decode_contents().strip()
                                if not re.search(r'\w(_|-)\w|\w\d+$', caption):
                                    captions.append(caption)
                        caption = ' | '.join(captions)
        if not item.get('_image') and post.get('_links') and post['_links'].get('wp:attachment'):
            for link in post['_links']['wp:attachment']:
                if not item.get('_image'):
                    if site_json.get('replace_links_path'):
                        link_json = utils.get_url_json(link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1]))
                    else:
                        link_json = utils.get_url_json(link['href'])
                    if link_json:
                        for it in link_json:
                            if it['media_type'] == 'image':
                                item['_image'] = it['source_url']
                                captions = []
                                if it.get('description'):
                                    soup = BeautifulSoup(it['description']['rendered'], 'html.parser')
                                    if not soup.find(class_=True):
                                        caption = soup.get_text().strip()
                                        if caption:
                                            captions.append(caption)
                                if not captions and it.get('caption'):
                                    soup = BeautifulSoup(it['caption']['rendered'], 'html.parser')
                                    if not soup.find(class_=True):
                                        #caption = soup.get_text().strip()
                                        caption = re.sub(r'^<p>(.*?)</p>$', r'\1', it['caption']['rendered'])
                                        if caption:
                                            captions.append(caption)
                                if not captions and it.get('title'):
                                    soup = BeautifulSoup(it['title']['rendered'], 'html.parser')
                                    if not soup.find(class_=True):
                                        caption = soup.get_text().strip()
                                        if caption and not re.search(r'\w(_|-)\w|\w\d+$', caption):
                                            captions.append(caption)
                                caption = ' | '.join(captions)
                                break
    if yoast_json:
        it = next((it for it in yoast_json['@graph'] if (it.get('@type') and it['@type'] == '@ImageObject')), None)
        if it:
            if it.get('contentUrl'):
                item['_image'] = it['contentUrl']
            elif it.get('url'):
                item['_image'] = it['url']
            if it.get('caption'):
                caption = it['caption']
    if not item.get('_image'):
        if post.get('yoast_head_json') and post['yoast_head_json'].get('og_image'):
            item['_image'] = post['yoast_head_json']['og_image'][0]['url']
        elif post.get('jetpack_featured_media_url'):
            item['_image'] = post['jetpack_featured_media_url']
        elif post.get('parselyMeta') and post['parselyMeta'].get('parsely-image-url'):
            item['_image'] = post['parselyMeta']['parsely-image-url']
        elif post.get('episode_featured_image'):
            item['_image'] = post['episode_featured_image']
        elif post.get('acf'):
            if post['acf'].get('hero') and post['acf']['hero'].get('image'):
                item['_image'] = post['acf']['hero']['image']
            elif post['acf'].get('post_hero') and post['acf']['post_hero'].get('image'):
                item['_image'] = post['acf']['post_hero']['image']
        elif post.get('im_images'):
            images = []
            for image in post['im_images']:
                if not image.get('crop'):
                    images.append(image)
            if images:
                image = utils.closest_dict(images, 'width', 1200)
                item['_image'] = image['url']
            else:
                item['_image'] = post['im_images'][0]['url']

    if item.get('_image'):
        item['_image'] = resize_image(item['_image'], site_json)

    if post.get('excerpt'):
        if isinstance(post['excerpt'], str):
            item['summary'] = post['excerpt']
        elif post['excerpt'].get('rendered') and isinstance(post['excerpt']['rendered'], str):
            item['summary'] = BeautifulSoup(post['excerpt']['rendered'], 'html.parser').get_text()
    if not item.get('summary'):
        if post.get('yoast_head_json'):
            if post['yoast_head_json'].get('description'):
                item['summary'] = post['yoast_head_json']['description']
            elif post['yoast_head_json'].get('og_description'):
                item['summary'] = post['yoast_head_json']['og_description']
        elif post.get('meta'):
            if post['meta'].get('summary'):
                item['summary'] = post['meta']['summary']
            elif post['meta'].get('long_summary'):
                item['summary'] = post['meta']['long_summary']
    if not item.get('summary') and yoast_json:
        it = next((it for it in yoast_json['@graph'] if it.get('description')), None)
        if it:
            item['summary'] = it['description']

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;"><a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a><div style="margin-left:8px; margin-right:8px;"><h4><a href="{}">{}</a></h4><p><small>{}</small></p></div></div>'.format(item['url'], item['_image'], item['url'], item['title'], item['summary'])
        return item

    content_html = ''
    # if post.get('content') and post['content'].get('structured'):
    #     logger.debug('getting structured content...')
    #     item['content_html'] = content_html + render_content(post['content']['structured'], item['url'])
    #     return item
    if post.get('content') and isinstance(post['content'], str):
        content_html += post['content']
    elif post.get('content') and post['content'].get('rendered'):
        if 'remove_vc_entities' in args:
            content_html += re.sub(r'\[(/?vc_[^\]]+)\]', '', post['content']['rendered'])
        else:
            content_html += post['content']['rendered']
        # utils.write_file(content_html, './debug/debug.html')
    elif post.get('acf'):
        for module in post['acf']['article_modules']:
            if module['acf_fc_layout'] == 'text_block':
                content_html += module['copy']
            elif module['acf_fc_layout'] == 'list_module':
                content_html += '<h3>{}</h3>'.format(module['title'])
                if module['list_type'] == 'video':
                    if 'youtube' in module['video_url']:
                        for yt in re.findall(r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})', module['video_url']):
                            content_html += utils.add_youtube(yt)
                    else:
                        logger.warning('unhandled video_url in ' + item['url'])
                else:
                    logger.warning('unhandled list_type {} in {}'.format(module['list_type'], item['url']))
                content_html += module['copy']
            elif module['acf_fc_layout'] == 'image_block':
                content_html += utils.add_image(resize_image(module['image'], site_json), module['caption'])
            elif module['acf_fc_layout'] == 'affiliates_block' or module['acf_fc_layout'] == 'inline_recirculation' or module['acf_fc_layout'] == 'membership_block':
                pass
            else:
                logger.warning('unhandled acf_fc_layout module {} in {}'.format(module['acf_fc_layout'], item['url']))
    elif post.get('type') and post['type'] == 'video':
        if post.get('excerpt') and post['excerpt'].get('rendered'):
            content_html += post['excerpt']['rendered']
        elif post.get('html_stripped_summary'):
            content_html += '<p>{}</p>'.format(post['html_stripped_summary'])
    else:
        logger.warning('unknown post content in ' + item['url'])

    content_html = content_html.replace('\u2028', '')

    lede = ''
    subtitle = ''
    if site_json.get('subtitle'):
        if not page_soup:
            page_html = utils.get_url_html(item['url'])
            if page_html:
                page_soup = BeautifulSoup(page_html, 'lxml')
        if page_soup:
            subtitles = []
            for el in utils.get_soup_elements(site_json['subtitle'], page_soup):
                subtitles.append(el.get_text())
            if subtitles:
                subtitle = '<br/>'.join(subtitles)
    else:
        if post.get('subtitle'):
            subtitle = post['subtitle']
        elif post.get('sub_headline'):
            subtitle = post['sub_headline']['raw']
        elif post.get('rayos_subtitle'):
            subtitle = post['rayos_subtitle']
        elif post.get('meta'):
            if post['meta'].get('sub_title'):
                subtitle = post['meta']['sub_title']
            elif post['meta'].get('nbc_subtitle'):
                subtitle = post['meta']['nbc_subtitle']
            elif post['meta'].get('sub_heading'):
                subtitle = post['meta']['sub_heading']
            elif post['meta'].get('subheadline'):
                subtitle = post['meta']['subheadline']
            elif post['meta'].get('dek'):
                subtitle = post['meta']['dek']
            elif post['meta'].get('lux_article_dek_field'):
                subtitle = post['meta']['lux_article_dek_field']
            elif post['meta'].get('long_summary'):
                subtitle = post['meta']['long_summary']
            elif post['meta'].get('multi_title'):
                multi_title = json.loads(post['meta']['multi_title'])
                if multi_title['titles']['headline'].get('additional') and multi_title['titles']['headline']['additional'].get('headline_subheadline'):
                    subtitle = multi_title['titles']['headline']['additional']['headline_subheadline']
            elif post['meta'].get('rappler-three-point-summary'):
                subtitle = '<ul>'
                for it in re.findall(r'"(.*?)"', ' '.join(post['meta']['rappler-three-point-summary'])):
                    subtitle += '<li>' + it + '</li>'
                subtitle += '</ul>'
        elif post.get('cmb2'):
            if post['cmb2'].get('articles_metabox') and post['cmb2']['articles_metabox'].get('_cmb_standfirst'):
                subtitle = '<p><em>{}</em></p>'.format(post['cmb2']['articles_metabox']['_cmb_standfirst'])
        if not subtitle and 'add_subtitle' in args and item.get('summary'):
            subtitle = item['summary']
    if subtitle:
        lede += '<p><em>{}</em></p>'.format(subtitle)

    if 'skip_lede_img' not in args:
        video_lede = ''
        if post.get('lead_media') and re.search(r'wp:lakana/anvplayer', post['lead_media']['raw']):
            ld_json = utils.get_ld_json(item['url'])
            if save_debug:
                utils.write_file(ld_json, './debug/ld_json.json')
            if ld_json:
                if isinstance(ld_json, list):
                    for it in ld_json:
                        if it['@type'] == 'NewsArticle':
                            article_json = it
                else:
                    article_json = ld_json
                for it in article_json['associatedMedia']:
                    if it['@type'] == 'VideoObject':
                        video_lede = utils.add_video(it['contentUrl'], 'application/x-mpegURL', it['thumbnailUrl'], it['name'])
                        break
        elif post.get('rj_fields') and post['rj_fields'].get('rj_field_vdo'):
            for it in post['rj_fields']['rj_field_vdo']:
                m = re.search(r'id="([^"]+)"', it)
                if m:
                    video_lede += utils.add_embed('https://embed.sendtonews.com/player3/embedcode.js?SC={}'.format(m.group(1)))
        elif post.get('meta') and post['meta'].get('_pmc_featured_video_override_data'):
            if post['meta']['_pmc_featured_video_override_data'].startswith('http'):
                video_lede += utils.add_embed(post['meta']['_pmc_featured_video_override_data'])
            else:
                m = re.search(r'connatix ([\-0-9a-f]+)', post['meta']['_pmc_featured_video_override_data'])
                if m:
                    media_id = m.group(1)
                    if not page_soup:
                        page_html = utils.get_url_html(item['url'])
                        if page_html:
                            page_soup = BeautifulSoup(page_html, 'lxml')
                    if page_soup:
                        el = page_soup.find('script', id='connatix_contextual_player_div_{}'.format(media_id))
                        if el:
                            m = re.search(r'playerId:\s?\'([\-0-9a-f]+)\'', el.string)
                            if m:
                                video_src = 'https://vid.connatix.com/pid-{}/{}/playlist.m3u8'.format(m.group(1), media_id)
                                poster = 'https://img.connatix.com/pid-{}/{}/1_th.jpg?width=1000&format=jpeg&quality=60'.format(m.group(1), media_id)
                                video_lede += utils.add_video(video_src, 'application/x-mpegURL', poster)
        elif post.get('meta') and ((post['meta'].get('media_pid') and post['meta']['video_provider'] == 'mpx') or (post['meta'].get('lede_video_id') and 'nbc' in split_url.netloc)):
            video_meta = None
            nbc_json = None
            if post['meta'].get('lede_video_id'):
                if not page_soup:
                    page_html = utils.get_url_html(item['url'])
                    if page_html:
                        page_soup = BeautifulSoup(page_html, 'lxml')
                if page_soup:
                    el = page_soup.find(attrs={"data-react-component": "VideoPlayer"})
                    if el:
                        video_meta = json.loads(html.unescape(el['data-meta']))
                    el = page_soup.find('script', string=re.compile(r'var nbc ='))
                    if el:
                        i = el.string.find('{')
                        j = el.string.rfind('}') + 1
                        nbc_json = json.loads(el.string[i:j])
            else:
                video_meta = post['meta']
            if video_meta:
                if nbc_json:
                    site_id = video_meta['syndicated_id'].split(':')[1]
                    for account_id, val in nbc_json['pdkAccounts'].items():
                        if site_id in val:
                            break
                    video_url = 'https://link.theplatform.com/s/{}/media/{}?formats=MPEG-DASH+widevine,M3U+appleHlsEncryption,M3U+none,MPEG-DASH+none,MPEG4,MP3&format=SMIL&fwsitesection={}&fwNetworkID={}&pprofile=ots_desktop_html&sensitive=false&usPrivacy=1YNN&w=655&h=368.4375&rnd={}&mode=on-demand&tracking=true&vpaid=script&schema=2.0&sdk=PDK+6.1.3'.format(account_id, video_meta['media_pid'], nbc_json['video']['fwSSID'], nbc_json['video']['fwNetworkID'], math.floor(random.random() * 10000000))
                else:
                    ssid = 'ots_{}_{}'.format(site_json['call_letters'], '_'.join(paths[:-2]))
                    video_url = 'https://link.theplatform.com/s/{}/media/{}?formats=MPEG-DASH+widevine,M3U+appleHlsEncryption,M3U+none,MPEG-DASH+none,MPEG4,MP3&format=SMIL&fwsitesection={}&fwNetworkID=382114&pprofile=ots_desktop_html&sensitive=false&usPrivacy=1YNN&w=655&h=368.4375&rnd={}&mode=on-demand&tracking=true&vpaid=script&schema=2.0&sdk=PDK+6.1.3'.format(site_json['account_id'], video_meta['media_pid'], ssid, math.floor(random.random() * 10000000))
                video_html = utils.get_url_html(video_url)
                if video_html:
                    video_soup = BeautifulSoup(video_html, 'html.parser')
                    el = video_soup.find('ref')
                    if el:
                        captions = []
                        if el.get('abstract'):
                            captions.append(el['abstract'])
                        elif post['meta'].get('video_captions'):
                            captions.append(post['meta']['video_captions'])
                        if el.get('author'):
                            captions.append(el['author'])
                        if el.get('copyright'):
                            captions.append(el['copyright'])
                        elif post['meta'].get('video_copyright'):
                            captions.append(post['meta']['video_copyright'])
                        video_lede += utils.add_video(el['src'], el['type'], video_meta.get('mpx_thumbnail_url'), ' | '.join(captions))
                    else:
                        captions = []
                        if video_meta.get('video_captions'):
                            captions.append(video_meta['video_captions'])
                        if video_meta.get('video_copyright'):
                            captions.append(video_meta['video_copyright'])
                        el = video_soup.find('video')
                        if el:
                            video_lede += utils.add_video(el['src'], 'application/x-mpegURL', video_meta.get('mpx_thumbnail_url'), ' | '.join(captions))
        elif post.get('meta') and post['meta'].get('featured_bc_video_id'):
            # https://www.thescottishsun.co.uk/news/11805626/bronson-battersby-died-alone-dead-dad/
            if not page_soup:
                page_html = utils.get_url_html(item['url'])
                if page_html:
                    page_soup = BeautifulSoup(page_html, 'lxml')
            if page_soup:
                el = page_soup.find('video', attrs={"data-video-id-pending": post['meta']['featured_bc_video_id']['id']})
                if el:
                    video_lede = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(el['data-account'], el['data-player'], el['data-video-id-pending']))
        elif post.get('you_tube_id'):
            video_lede = utils.add_embed('https://www.youtube.com/watch?v=' + post['you_tube_id'])
        elif site_json.get('lede_video'):
            if not page_soup:
                page_html = utils.get_url_html(item['url'])
                if page_html:
                    page_soup = BeautifulSoup(page_html, 'lxml')
            if page_soup:
                el = page_soup.find(site_json['lede_video']['tag'], attrs=site_json['lede_video']['attrs'])
                if el:
                    it = el.find(class_='c-videoPlay')
                    if it and it.get('data-displayinline'):
                        video_lede = utils.add_embed(it['data-displayinline'])
        if video_lede:
            lede += video_lede
        elif item.get('_image'):
            if '.mp4.' in item['_image']:
                video_src = item['_image'].split('.mp4')[0] + '.mp4'
                lede += utils.add_video(video_src, 'video/mp4', item['_image'])
            elif not re.search(urlsplit(item['_image']).path, content_html, flags=re.I) or 'add_lede_img' in args:
                # Add lede image if it's not in the content or if add_lede_img arg
                lede += utils.add_image(item['_image'], caption)
        elif site_json.get('lede_img'):
            if not page_soup:
                page_html = utils.get_url_html(item['url'])
                if page_html:
                    page_soup = BeautifulSoup(page_html, 'lxml')
            if page_soup:
                elements = utils.get_soup_elements(site_json['lede_img'], page_soup)
                if elements:
                    lede += add_image(elements[0], elements[0], base_url, site_json)

    if post.get('acf') and post['acf'].get('post_hero') and post['acf']['post_hero'].get('number_one_duration'):
        # https://www.stereogum.com/2211784/the-number-ones-chamillionaires-ridin-feat-krayzie-bone/columns/the-number-ones/
        lede += '<div style="font-size:1.1em; font-weight:bold; text-align:center;">{}<br/>Weeks at #1: {}<br/>Rating: {}</div>'.format(post['acf']['post_hero']['chart_date'], post['acf']['post_hero']['number_one_duration'], post['acf']['post_hero']['rating'])

    # Review summary
    if post.get('wppr_data') and post['wppr_data'].get('_wppr_review_template'):
        lede += '<div style="text-align:center;"><h2>{}</h2>'.format(post['wppr_data']['cwp_rev_product_name'])
        lede += '<h3><span style="font-size:2em;">{:.1f}</span>/10</h3>'.format(float(post['wppr_data']['wppr_rating'])/10)
        if 'techaeris.com' in item['url']:
            lede += '<img src="https://techaeris.com/wp-content/uploads/2017/03/TA-ratings-{:.0f}.png"/>'.format(float(post['wppr_data']['wppr_rating']))
            soup = BeautifulSoup(post['content']['rendered'], 'html.parser')
            el = soup.find('img', attrs={"src": re.compile(r'EDITORS-CHOICE|HIGHLY-RATED|TOP-PICK')})
            if el:
                lede += '<img src="{}"/>'.format(el['src'])
                el.find_parent('div', class_='wp-block-image').decompose()
            el = soup.find('img', attrs={"src": re.compile(r'TA-ratings-\d+.png')})
            if el:
                el.find_parent('div', class_='wp-block-image').decompose()
            post['content']['rendered'] = str(soup)
        lede += '</div>'
        if post['wppr_data'].get('wppr_options'):
            lede += '<h3>Scores</h3><table style="margin-left:1.5em;">'
            for key, val in post['wppr_data']['wppr_options'].items():
                lede += '<tr><td>{}</td><td>{:.1f}</td></tr>'.format(val['name'], float(val['value'])/10)
            lede += '</table>'
        if post['wppr_data'].get('wppr_pros'):
            lede += '<h3>Pros</h3><ul>'
            for it in post['wppr_data']['wppr_pros']:
                if it:
                    lede += '<li>{}</li>'.format(it)
            lede += '</ul>'
        if post['wppr_data'].get('wppr_cons'):
            lede += '<h3>Cons</h3><ul>'
            for it in post['wppr_data']['wppr_cons']:
                if it:
                    lede += '<li>{}</li>'.format(it)
            lede += '</ul>'
        if post['wppr_data'].get('wppr_links'):
            if post['wppr_data'].get('cwp_rev_price'):
                lede += '<h3>Buy: {}</h3><ul>'.format(post['wppr_data']['cwp_rev_price'])
            else:
                lede += '<h3>View</h3><ul>'
            for key, val in post['wppr_data']['wppr_links'].items():
                lede += '<li><a href="{}">{}</a></li>'.format(val, key)
            lede += '</ul>'
    elif post.get('meta') and post['meta'].get('game_report_card'):
        lede += '<table style="border:1px solid black; border-radius:10px; padding:8px; margin:8px;"><tr><td>'
        if post['meta'].get('xe_rating'):
            lede += '<span style="font-size:3em; font-weight:bold; padding:0.3em;">{}</span>'.format(post['meta']['xe_rating'])
        lede += '</td><td style="width:99%;">'
        for it in post['meta']['game_report_card']:
            if it['report_type_id'] == '1.0':
                lede += '➕&nbsp;{}<br/>'.format(it['report'])
            elif it['report_type_id'] == '2.0':
                lede += '➖&nbsp;{}<br/>'.format(it['report'])
        lede += '</td></tr></table>'

    if re.search('makezine\.com/(projects|products)', item['url']):
        if not page_soup:
            page_html = utils.get_url_html(item['url'])
            if page_html:
                page_soup = BeautifulSoup(page_html, 'lxml')
        if page_soup:
            if '/projects/' in item['url']:
                lede += '<h2><u>Project Steps</u></h2>'
                for el in page_soup.find_all(class_='project-step'):
                    it = el.find(class_='step-buttons')
                    if it:
                        it.decompose()
                    lede += el.decode_contents()
            elif '/products/' in item['url']:
                el = page_soup.find(class_='why-buy')
                if el:
                    if el.h4:
                        el.h4.decompose()
                    lede += '<h2>Why Buy?</h2>' + el.decode_contents()
                el = page_soup.find('table', id='specs')
                if el:
                    el.attrs = {}
                    it = el.find('tr', class_='table-title')
                    if it:
                        it.decompose()
                    lede += '<h2>Specs</h2>' + str(el)

    if post.get('audio') and 'add_audio' in args:
        # https://wamu.org/story/23/10/05/a-bumpy-vaccine-rollout-and-the-ongoing-risks-of-covid/
        lede += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen</a></span></div>'.format(post['audio']['audioFile'], config.server)

    footer = ''
    if 'add_content' in site_json:
        if not page_soup:
            page_html = utils.get_url_html(item['url'])
            if page_html:
                page_soup = BeautifulSoup(page_html, 'lxml')
        for it in site_json['add_content']:
            sep_lede = False
            sep_foot = False
            elements = utils.get_soup_elements(it, page_soup)
            if elements:
                for el in elements:
                    if it['position'] == 'top':
                        lede += str(el)
                        if it.get('separator'):
                            sep_lede = True
                    else:
                        footer += str(el)
                        if it.get('separator'):
                            sep_foot = True
            if sep_lede == True:
                lede += '<div>&nbsp;</div><hr style="width:80%; margin:auto;"/><div>&nbsp;</div>'
            if sep_foot == True:
                footer = '<div>&nbsp;</div><hr style="width:80%; margin:auto;"/><div>&nbsp;</div>' + footer

    item['content_html'] = format_content(lede + content_html + footer, item, site_json)

    # if re.search('makezine\.com/(projects|products)', item['url']):
    #     page_html = utils.get_url_html(item['url'])
    #     utils.write_file(page_html, './debug/debug.html')
    #     if page_html:
    #         if '/projects/' in item['url']:
    #             item['content_html'] += '<h2><u>Project Steps</u></h2>'
    #             soup = BeautifulSoup(page_html, 'lxml')
    #             for el in soup.find_all(class_='project-step'):
    #                 item['content_html'] += el.decode_contents()
    #             ld_json = []
    #             for m in re.findall(r'<script[^>]+type=\"application/ld\+json\">(.*?)</script>', page_html, flags=re.S):
    #                 ld_json.append(json.loads(m))
    #             if ld_json:
    #                 ld = next((it for it in ld_json if it.get('@type') == 'HowTo'), None)
    #                 if ld:
    #                     item['content_html'] += '<h2><u>Project Steps</u></h2>'
    #                     for i, step in enumerate(ld['step']):
    #                         if re.search('^\d', step['name']):
    #                             item['content_html'] += '<h2>{}</h2>'.format(step['name'])
    #                         else:
    #                             item['content_html'] += '<h2>{}. {}</h2>'.format(i+1, step['name'])
    #                         if step.get('image'):
    #                             item['content_html'] += utils.add_image(step['image']['url'])
    #                         for it in step['itemListElement']:
    #                             item['content_html'] += '<p>{}</p>'.format(it['text'])
    #         elif '/products/' in item['url']:
    #             soup = BeautifulSoup(page_html, 'lxml')
    #             el = soup.find(class_='why-buy')
    #             if el:
    #                 if el.h4:
    #                     el.h4.decompose()
    #                 item['content_html'] += '<h2>Why Buy?</h2>' + el.decode_contents()
    #             el = soup.find('table', id='specs')
    #             if el:
    #                 el.attrs = {}
    #                 it = el.find('tr', class_='table-title')
    #                 if it:
    #                     it.decompose()
    #                 item['content_html'] += '<h2>Specs</h2>' + str(el)
    return item


def format_content(content_html, item, site_json=None, module_format_content=None):
    #utils.write_file(content_html, './debug/debug.html')
    split_url = urlsplit(item['url'])
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)

    soup = BeautifulSoup(content_html, 'html.parser')
    el = soup.find(class_='entry-content')
    if el:
        soup = el

    for el in soup.find_all(text=lambda text: isinstance(text, Comment)):
        el.extract()

    # Remove site-specific elements
    if site_json and site_json.get('decompose'):
        for it in site_json['decompose']:
            for el in utils.get_soup_elements(it, soup):
                el.decompose()

    if site_json and site_json.get('unwrap'):
        for it in site_json['unwrap']:
            for el in utils.get_soup_elements(it, soup):
                el.unwrap()

    el = soup.find('body')
    if el:
        soup = el

    utils.write_file(str(soup), './debug/debug.html')

    # Format module specific content
    if module_format_content:
        module_format_content(soup, item, site_json=None)

    el = soup.find(class_='blog-post-info')
    if el:
        el.unwrap()

    # Use site-specific elements when possible
    # for el in soup.find_all(class_=re.compile(r'ad-aligncenter|c-message_kit__gutter|daily_email_signup||figma-framed|inline-auto-newsletter|patreon-campaign-banner|patreon-text-under-button|sailthru_shortcode|simpletoc-|staticendofarticle|steps-shortcut-wrapper|yoast-table-of-contents|wp-polls')):
    #     el.decompose()

    for el in soup.find_all(class_=re.compile(r'^ad_|\bad\b|injected-related-story|link-related|nlp-ignore-block|related_links|related-stories|sharedaddy|signup-widget|wp-block-bigbite-multi-title|wp-block-product-widget-block')):
        el.decompose()

    for el in soup.find_all(id=re.compile(r'^ad_|\bad\b|related')):
        el.decompose()

    for el in soup.find_all(class_='fs-shortcode'):
        if el.find(class_='story-link-next'):
            el.decompose()

    for el in soup.find_all('section', class_=re.compile('wp-block-newsletterglue')):
        el.decompose()

    for el in soup.find_all(id=['ez-toc-container', 'toc_container']):
        el.decompose()

    for el in soup.find_all(['meta', 'noscript']):
        el.decompose()

    for el in soup.find_all(id='piano-meter-offer'):
        el.unwrap()

    for el in soup.find_all('div', class_=re.compile(r'GutenbergParagraph_gutenbergParagraph_')):
        el.unwrap()

    for el in soup.find_all('div', class_=re.compile(r'gb-grid-wrapper|gb-container')):
        for it in el.find_all(class_='gb-inside-container'):
            el.insert_before(it)
            it.unwrap()
        el.decompose()

    for el in soup.find_all('svg', attrs={"data-icon": True}):
        new_html = ''
        if el['data-icon'] == 'clock':
            new_html = '<span>&#128337;</span>'
        elif el['data-icon'] == 'long-arrow-alt-right':
            new_html = '<span>&#10230;</span>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled svg data-icon {} in {}'.format(el['data-icon'], item['url']))

    for el in soup.find_all('img', class_='emoji'):
        new_html = ''
        split_src = urlsplit(el['src'])
        if split_src.netloc == 's.w.org':
            src_paths = list(filter(None, split_src.path[1:].split('/')))
            m = re.findall(r'([0-9a-f]+)', src_paths[-1])
            if m:
                new_html = '<span>'
                for it in m:
                    new_html += '&#{};'.format(int(it, 16))
                    #new_html += '&#x{};'.format(it)
                new_html += '</span>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled emoji in ' + item['url'])

    for el in soup.find_all(re.compile(r'^h\d')):
        it = el.find(attrs={"style": True})
        if it:
            it.unwrap()

    for el in soup.find_all(['h5', 'h6']):
        # too small
        el.name = 'h4'

    for el in soup.find_all('span', class_='neFMT_Subhead_WithinText'):
        el['style'] = 'font-size:1.2em; font-weight:bold;'

    for el in soup.find_all('table', attrs={"width": True}):
        el.attrs = {}
        el['style'] = 'width:100%;'

    for el in soup.find_all(class_='has-text-align-center'):
        el['style'] = 'text-align:center;'

    for el in soup.find_all(class_='summary__title'):
        new_html = '<h2>{}</h2>'.format(el.get_text())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-group'):
        if el.find(id='mc_embed_signup'):
            el.decompose()
        elif split_url.netloc == 'www.smartprix.com':
            it = el.find(class_='wp-block-group__inner-container')
            if it:
                kbds = it.find_all('kbd')
                ratings = it.find_all('div', class_='wp-block-jetpack-rating-star')
                n = len(ratings)
                new_html = '<table>'
                for i, kbd in enumerate(kbds):
                    new_html += '<tr><td>{}</td><td>'.format(str(kbd))
                    if i < n:
                        rating = ratings[i].find(attrs={"itemprop": "ratingValue"})
                        if rating:
                            val = float(rating['content'])
                            for j in range(math.floor(val)):
                                new_html += '&#9733;'
                            if val % 1:
                                new_html += '&#x00BD;'
                    new_html += '</td></tr>'
                new_html += '</table>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

    for el in soup.find_all(class_='wp-block-buttons'):
        it = el.find(class_='wp-block-button__link')
        if it:
            new_html = '<div><a href="{}"><span style="display:inline-block; min-width:180px; text-align: center; padding:0.5em; font-size:0.8em; text-transform:uppercase; border:1px solid rgb(5, 125, 188);">{}</span></a></div>'.format(it['href'], it.get_text())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-buttons in ' + item['url'])

    for el in soup.find_all(class_='wp-block-prc-block-subtitle'):
        new_html = '<p><em>{}</em></p>'.format(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        soup.insert(0, new_el)
        el.decompose()

    for el in soup.find_all('p', class_=['has-drop-cap', 'dropcap', 'drop-cap', 'add-drop-cap']):
        new_html = re.sub(r'>("?\w)', r'><span style="float:left; font-size:4em; line-height:0.8em;">\1</span>', str(el), 1)
        new_html += '<span style="clear:left;"></span>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('span', class_=['dropcap', 'drop-cap']):
        el.attrs = {}
        el['style'] = 'float:left; font-size:4em; line-height:0.8em;'
        new_el = BeautifulSoup('<span style="clear:left;"></span>', 'html.parser')
        el.find_parent('p').insert_after(new_el)

    for el in soup.find_all('span', class_='has-underline'):
        el['style'] = 'text-decoration:underline; text-transform:uppercase; font-weight:bold;'

    for el in soup.find_all(class_='uppercase'):
        if el.get('style'):
            el['style'] += 'text-transform:uppercase; font-weight:bold;'
        else:
            el['style'] = 'text-transform:uppercase; font-weight:bold;'

    for el in soup.find_all('p', class_='has-small-font-size'):
        el['style'] = 'font-size:0.9em;'

    for el in soup.find_all('span', class_='section-lead'):
        el.name = 'strong'
        el.attrs = {}

    for el in soup.find_all(class_='c-message_actions__container'):
        # https://theathletic.com/3900893/2022/11/16/deshaun-watson-return-browns/
        it = el.find(class_='c-message_actions__group')
        it.name = 'p'
        it.attrs = {}
        el.insert_after(it)
        el.decompose()

    for el in soup.find_all(class_='aawp'):
        # https://home-assistant-guide.com/review/xiaomi-mi-robot-vacuum-mop-1c-long-term-review-a-cheap-option-that-integrates-with-home-assistant/
        # https://home-assistant-guide.com/review/adguard-home-vs-pi-hole-2020-two-ad-and-internet-tracker-blockers-compared/
        new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.find('a', class_=['aawp-product__image-link', 'aawp-product__image--link'])
        if it:
            img = it.find('img')
            if img:
                img_src = ''
                if img.get('data-src'):
                    img_src = img['data-src']
                elif img.get('src'):
                    img_src = img['src']
                if img_src:
                    new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><a href="{}"><img style="width:100%;" src="{}"/></a></div>'.format(it['href'], img_src)
        new_html += '<div style="flex:2; min-width:256px;">'
        it = el.find('a', class_='aawp-product__title')
        if it:
            new_html += '<div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(it['href'], it.get_text().strip())
        it = el.find(class_='aawp-product__price')
        if it:
            new_html += '<div>{}</div>'.format(it.get_text().strip())
        it = el.find('a', class_='aawp-button')
        if it:
            new_html += '<div><a href="{}">{}</a></div>'.format(it['href'], it.get_text().strip())
        new_html += '</div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(id=re.compile(r'the-good|the-bad|the-ugly')):
        el.attrs = {}
        new_html = '<ul>'
        for it in el.find_next_siblings():
            if it.get('class') and 'gb-headline' in it['class']:
                new_html += '<li>{}</li>'.format(it.get_text())
                it.decompose()
            else:
                break
        new_html += '</ul>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)

    for el in soup.find_all(class_='product-card'):
        # https://spy.com/articles/lifestyle/food-drink/best-mushroom-coffees-1202954039/
        new_html = '<hr/><div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.find(class_='product-card-image-wrapper')
        if it:
            new_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(add_image(it, None, base_url, site_json).replace('width:100%;', 'width:auto; max-height:300px;'))
        new_html += '<div style="flex:1; min-width:256px;">'
        it = el.find(class_='article-kicker')
        if it:
            new_html += '<div style="margin-top:0.5em; margin-bottom:0.5em; text-align:center;"><span style="padding:0.4em; font-weight:bold; color:white; background-color:#153969;">{}</span></div>'.format(it.get_text().strip())
        it = el.find(class_='c-title')
        if it:
            new_html += '<div style="font-size:1.2em; font-weight:bold; text-align:center;">{}</div>'.format(it.get_text().strip())
        it = el.find(class_='buy-now-buttons')
        if it:
            if it.p:
                new_html += '<div style="font-size:1.1em; font-weight:bold; text-align:center;">{}</div>'.format(it.p.span.get_text())
            new_html += '<div style="margin-top:0.5em; margin-bottom:0.5em; text-align:center;"><span style="padding:0.4em; font-weight:bold; background-color:rgb(255,213,53);"><a href="{}">{}</a></span></div>'.format(it.a['href'], it.a.get_text().strip())
        it = el.find(class_='c-dek')
        if it:
            it.attrs = {}
            new_html += str(it)
        new_html += '</div></div><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='spy__buy-now-wrapper'):
        # https://spy.com/articles/gadgets/electronics/bluetti-power-system-release-1202949586/
        new_html = ''
        it = el.find(class_='spy__link')
        if it:
            link = utils.get_redirect_url(it['href'])
            data_json = json.loads(it['custom-ga-data'])
            new_html += '<div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(link, data_json['product']['name'])
            new_html += '<div style="font-size:1.1em; font-weight:bold;">${}</div>'.format(data_json['product']['price'])
            new_html += '<div style="margin-top:0.5em; margin-bottom:0.5em;"><span style="padding:0.4em; font-weight:bold; background-color:rgb(255,213,53);"><a href="{}">Buy Now</a></span></div><div>&nbsp;</div>'.format(link)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled spy__buy-now-wrapper in ' + item['url'])

    for el in soup.find_all(class_='wp-block-columns'):
        # https://jamesachambers.com/radxa-zero-debian-ssd-boot-guide/
        new_html = '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        for it in el.find_all(class_='wp-block-column'):
            img = it.find(class_='wp-block-image')
            if img and img.img:
                if img.img.get('srcset'):
                    img_src = utils.image_from_srcset(img.img['srcset'], 160)
                else:
                    img_src = img.img['src']
                new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><img style="width:100%;" src="{}"/></div>'.format(img_src)
            else:
                new_html += '<div style="flex:2; min-width:256px;">{}</div>'.format(it.decode_contents())
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='review-wrapper'):
        # https://the5krunner.com/2023/01/11/magene-l508-review-smart-radar-tail-light/
        review_html = '<hr/><div>'
        img = el.find('img')
        if img:
            review_html += '<img src="{}" style="float:left; margin-right:8px; width:128px;"/>'.format(img['src'])
            it.decompose()
        # else:
        #     review_html += '<img src="{}/image?width=24&height=24&color=none" style="float:left; margin-right:8px;"/>'.format(config.server)
        review_html += '<div style="overflow:hidden;">'
        it = el.find(class_='review-title')
        if it:
            review_html += '<p style="font-size:1.2em; font-weight:bold;">{}</p>'.format(it.get_text().strip())
        if img:
            review_html += '</div><div style="clear:left;">&nbsp;</div>'
        it = el.find(class_='review-total-box')
        if it:
            review_html += '<h3>Score: <span style="font-size:2em; font-weight:bold;">{}</span></h3>'.format(it.get_text())
        else:
            review_html += '<h3>Scores</h3>'
        for it in el.find_all(class_='review-point'):
            it.decompose()
        it = el.find(class_='review-list')
        if it:
            review_html += '<table style="margin-left:1.5em;">'
            for li in it.find_all('li'):
                review_html += '<tr><td>{}</td>'.format(re.sub(r' - [\d\s%]+$', '', li.get_text().strip()))
                score = ''
                result = li.find('div', class_='review-result-text')
                if result:
                    score = result.get_text().strip()
                else:
                    result = li.find('div', class_='review-result', attrs={"style": re.compile(r'width:\d+')})
                    if result:
                        m = re.search(r'width:(\d+)', result['style'])
                        if m:
                            score = '{:.1f}'.format(int(m.group(1)) / 20)
                if score:
                    review_html += '<td>{}</td></tr>'.format(score)
                else:
                    review_html += '<td></td></tr>'
            review_html += '</table>'
        it = el.find(class_='review-desc')
        if it:
            review_html += '<h3>Summary</h3><div style="margin-left:1.5em;">{}</div>'.format(it.decode_contents())
        it = el.find(class_='review-pros')
        if it:
            review_html += '<h3>Pros</h3>' + str(it.find('ul'))
        it = el.find(class_='review-cons')
        if it:
            review_html += '<h3>Pros</h3>' + str(it.find('ul'))
        it = el.find('ul', class_='review-links')
        if it:
            review_html += '<h3>Links</h3>' + str(it)
        new_el = BeautifulSoup(review_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='reviewBox'):
        # https://twinfinite.net/2023/01/one-piece-odyssey-review/
        review_html = ''
        it = el.find('img', class_='review-image')
        if it:
            review_html += utils.add_image(resize_image(it['src'], site_json))
        it = el.find(class_='review-title')
        if it:
            review_html += '<div style="text-align:center; font-size:1.3em; font-weight:bold">{}</div>'.format(it.get_text().strip())
        it = el.find(class_='reviewScoreVal')
        if it:
            review_html += '<div style="text-align:center;"><span style="font-size:2em; font-weight:bold;">{}</span>'.format(it.get_text().strip())
            it = el.find(class_='outOF')
            if it:
                review_html += ' {}'.format(it.get_text().strip())
            it = el.find(class_='review-highlight')
            if it:
                review_html += '<br/><span style="font-size:1.2em; font-style:italic;">{}</span>'.format(it.get_text().strip())
            it = el.find('img', attrs={"src": re.compile(r'Editors-Choice')})
            if it:
                review_html += '<br/><img src="{}" style="width:128px;"/>'.format(resize_image(it['src'], site_json, 128))
            it = el.find(class_='officialScore')
            if it:
                review_html += '<p>{}</p>'.format(it.decode_contents())
            review_html += '</div>'
        for it in el.find_all(class_='reviewPros'):
            review_html += '<h3>{}</h3><ul>'.format(it.h4.get_text().strip())
            for li in it.find_all('li'):
                review_html += '<li>{}</li>'.format(li.get_text().strip())
            review_html += '</ul>'
        it = el.find(class_='gameInfo')
        if it:
            review_html += '<h3>Game info</h3><ul>'
            for li in it.find_all('div', class_=True):
                review_html += '<li>{}: '.format(li.span.extract().get_text().strip())
                review_html += '{}</li>'.format(li.get_text().strip())
            review_html += '</ul>'
        new_el = BeautifulSoup(review_html, 'html.parser')
        if el.parent and el.parent.name == 'div':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()
        it = soup.find(class_='reviewLabBox')
        if it:
            it.decompose()

    for el in soup.find_all(id='review-body'):
        # This is probably specific to techhive.com
        review_html = '<br/><div><div style="text-align:center">'
        if el.find('img', src=re.compile(r'Editors-Choice')):
            review_html += '<span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span><br />'
        it = el.find(class_='starRating')
        if it:
            m = re.search(r'([\d\.]+) out of 5', it['aria-label'])
            if m:
                review_html += '<h1 style="margin:0;">{} / 5</h1>'.format(m.group(1))
        review_html += '</div>'
        it = el.find('p', class_='verdict')
        if it:
            review_html += '<p><em>{}</em></p>'.format(it.get_text())
        it = el.find('ul', class_='pros')
        if it:
            review_html += '<strong>Pros</strong><ul>'
            for li in it.find_all('li'):
                review_html += '<li>{}</li>'.format(li.get_text())
            review_html += '</ul>'
        it = el.find('ul', class_='cons')
        if it:
            review_html += '<strong>Cons</strong><ul>'
            for li in it.find_all('li'):
                review_html += '<li>{}</li>'.format(li.get_text())
            review_html += '</ul>'
        it = el.find('p', class_='verdict')
        if it:
            it.attrs = {}
            review_html += '<strong>Our Verdict</strong>' + str(it)
        it = soup.find(class_='review-best-price')
        if it:
            for sib in it.next_siblings:
                if sib.name:
                    break
            if sib.get('class') and 'wp-block-price-comparison' in sib['class']:
                review_html += '<strong>Best Prices Today</strong><ul>'
                for record in sib.find_all(class_='price-comparison__record'):
                    if 'price-comparison__record--header' in record['class'] or 'price-comparison__record--footer' in record['class']:
                        continue
                    price = record.find(class_='price-comparison__price').get_text().strip()
                    image = record.find(class_='price-comparison__image')
                    if image.img:
                        vendor = image.img['alt']
                    else:
                        vendor = image.get_text().strip()
                    review_html += '<li>{} from <a href="{}">{}</a></li>'.format(price, utils.get_redirect_url(record.a['href']), vendor)
                review_html += '</ul>'
                sib.decompose()
            it.decompose()
        it = soup.find(class_='review-price')
        if it:
            for sib in it.next_siblings:
                if sib.name:
                    break
            sib.decompose()
            it.decompose()
        review_html += '<hr style="width:80%;"/>'
        new_el = BeautifulSoup(review_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='review-summary-box'):
        # https://www.destructoid.com/reviews/review-the-last-of-us-part-2-remastered/
        new_html = '<div style="text-align:center;">'
        it = el.find(class_='review-score')
        if it:
            new_html += '<div style="font-size:2em; font-weight:bold;">{}</div>'.format(it.get_text().strip())
        it = el.find(class_='review-title')
        if it:
            new_html += '<div style="font-size:1.2em; font-weight:bold;"><em>{}</em></div>'.format(it.get_text().strip())
        it = el.find(class_='review-text')
        if it:
            new_html += str(it)
        new_html += '</div><hr/><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-kelseymedia-blocks-block-stuff-says'):
        new_html = '<table style="width:100%;">'
        it = el.find(class_='c-stuff-says__title')
        if it:
            new_html += '<tr style="background-color:#555555;"><td colspan="2"><span style="color:white; font-size:1.1em; font-weight:bold;">{}</span></td></tr>'.format(it.get_text())
        new_html += '<tr><td style="width:50%;">'
        it = el.find(class_='c-stuff-says__rating-text')
        if it:
            new_html += '<span style="font-size:1.2em; font-weight:bold;">{}</span>'.format(it.get_text())
        new_html += '</td><td style="width:50%; text-align:right;"><span style="font-size:1.2em; color:red;">'
        it = el.find(class_='c-stuff-says__rating-score')
        if it:
            n = int(it.get_text())
            for i, it in enumerate(el.find_all(class_='c-star')):
                if i < n:
                    new_html += '★'
                else:
                    new_html += '☆'
        new_html += '</span></td></tr>'
        it = el.find(class_='c-stuff-says__verdict')
        if it:
            new_html += '<tr><td colspan="2"><em>{}</em></td></tr>'.format(it.get_text())
        new_html += '<tr><td style="width:50%;">'
        it = el.find(class_='c-stuff-says__good-stuff-title')
        if it:
            new_html += it.get_text()
        for it in el.find_all(class_='c-stuff-says__good-stuff-item'):
            new_html += '<br/>➕&nbsp;{}'.format(it.get_text())
        new_html += '</td><td style="width:50%;">'
        it = el.find(class_='c-stuff-says__bad-stuff-title')
        if it:
            new_html += it.get_text()
        for it in el.find_all(class_='c-stuff-says__bad-stuff-item'):
            new_html += '<br/>➖&nbsp;{}'.format(it.get_text())
        new_html += '</td></tr></table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='ub_review_block'):
        new_html = '<table style="border:1px solid black; border-radius:10px; padding:8px; margin:8px;">'
        it = el.find(class_='ub_review_item_name')
        if it:
            new_html += '<tr><td colspan="2"><span style="font-size:1.2em; font-weight:bold;">{}</span><br/><br/></td></tr>'.format(it.get_text())
        for i, it in enumerate(el.find_all(class_='ub_review_entry')):
            if i%2 == 1:
                color = 'background-color:lightgrey;'
            else:
                color = 'background-color:rgba(0,0,0,0);'
            new_html += '<tr><td style="{}">{}</td>'.format(color, it.find('span').get_text())
            rating = 0.0
            for star in it.find_all('svg'):
                mask = star.find('rect', attrs={"fill": "#fff"})
                if mask.get('width'):
                    rating += float(mask['width']) / 150.0
            new_html += '<td style="text-align:center; {}">{:.1f}</td></tr>'.format(color, rating)
        it = soup.find('script', attrs={"type": "application/ld+json"})
        if it:
            ld_json = json.loads(it.string)
            #utils.write_file(ld_json, './debug/ld_json.json')
            new_html += '<tr><td><br/><b>Summary</b><br/>{}</td><td><span style="font-size:2em; font-weight:bold; padding:0.3em;">{}</span></td></tr>'.format(ld_json['reviewBody'], ld_json['reviewRating']['ratingValue'])
            if ld_json['itemReviewed'].get('offers'):
                new_html += '<tr><td colspan="2" style="text-align:center;"><a href="{}">Buy {}</a></td></tr>'.format(ld_json['itemReviewed']['offers']['url'], ld_json['itemReviewed']['name'])
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='lets-review-block__wrap'):
        # https://press-start.com.au/reviews/xbox-series-x-reviews/2023/05/22/planet-of-lana-review/
        new_html = '<table style="border:1px solid black; border-radius:10px; padding:8px; margin:8px;">'
        it = soup.find('script', attrs={"type": "application/ld+json"})
        if it:
            ld_json = json.loads(it.string)
            #utils.write_file(ld_json, './debug/ld_json.json')
            new_html += '<tr><td colspan="2" style="text-align:center;"><span style="font-size:2em; font-weight:bold;">{}</span> / {}</td></tr>'.format(ld_json['review']['reviewRating']['ratingValue'], ld_json['review']['reviewRating']['bestRating'])
        it = el.find(class_='lets-review-block__conclusion')
        if it:
            new_html += '<tr><td colspan="2" style="padding:1em 0 1em 0;"><em>{}</em></td></tr>'.format(it.get_text())
        if el.find(class_='lets-review-block__proscons'):
            new_html += '<tr><td style="width:50%; vertical-align:top;"><b>Positives</b>'
            for it in el.find_all(class_='lets-review-block__pro'):
                new_html += '<br/>➕&nbsp;{}'.format(it.get_text())
            new_html += '</td><td style="width:50%; vertical-align:top;"><b>Negatives</b>'
            for it in el.find_all(class_='lets-review-block__con'):
                new_html += '<br/>➖&nbsp;{}'.format(it.get_text())
            new_html += '</td></tr>'
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='ta_game__metaBar__rating'):
        new_html = '<p><b>{}</b> <span style="font-size:2em; font-weight:bold;">'.format(el.get_text().strip())
        for it in el.find_all(class_=re.compile('mdi-star')):
            if 'mdi-star' in it['class']:
                new_html += '★'
            elif 'mdi-star-half' in it['class']:
                new_html += '½'
            # elif 'mdi-star-outline':
            #     new_html += '☆'
        new_html += '</span></p>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(id='rank-math-rich-snippet-wrapper'):
        # https://pocketables.com/2023/12/aohi-magcube-3-port-140-gan-travel-charger-juice-your-laptop-and-devices-faster.html
        new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.find(class_='rank-math-review-image')
        if it:
            if it.img['src'].startswith('data:image'):
                img_src = it.img['data-src']
            else:
                img_src = it.img['src']
            new_html += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%;"/></div>'.format(img_src)
        new_html += '<div style="flex:1; min-width:256px;">'
        it = el.find(class_='rank-math-title')
        if it:
            new_html += '<div style="font-size:1.2em; font-weight:bold; text-align:center;">' + it.get_text() + '</div><div>&nbsp;</div>'
        it = el.find(class_='rank-math-review-data')
        if it:
            for p in it.find_all('p'):
                if p.get_text().strip():
                    new_html += str(p)
        new_html += '</div></div><div>'
        it = el.find(class_='rank-math-total')
        if it:
            new_html += '<div style="text-align:center;"><strong>Rating:</strong> <span style="font-size:2em; font-weight:bold;">{}</span></div>'.format(it.get_text().strip())
        it = el.find(class_='rank-math-review-notes rank-math-review-pros')
        if it:
            new_html += it.decode_contents()
        it = el.find(class_='rank-math-review-notes rank-math-review-cons')
        if it:
            new_html += it.decode_contents()
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='bgr-product-review-block'):
        # https://bgr.com/reviews/samsung-galaxy-z-flip-5-review/
        new_html = '<div style="border:1px solid black; margin:8px; padding:8px;">'
        info = el.find(class_='bgr-product-review-info')
        if info:
            new_html += '<div><div style="text-align:center;">'
            it = info.find('h3')
            if it:
                new_html += '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(it.get_text())
            it = info.find(class_='sr-only')
            if it:
                m = re.search(r'[\d\.]+', it.get_text())
                if m:
                    new_html += '<div style="font-size:2em; font-weight:bold;">'
                    n = float(m.group(0))
                    for i in range(math.floor(n)):
                        new_html += '★'
                    if n % 1 > 0.0:
                        new_html += '½'
                    new_html += '</div>'
            it = info.find('image', attrs={"xlink:href": True})
            if it:
                new_html += '<img src="{}" style="width:128px;"/>'.format(it['xlink:href'])
            new_html += '</div>'
            it = info.find('p')
            if it:
                new_html += it.parent.decode_contents()
            new_html += '</div>'
        if el.find(class_='bgr-product-review-pros-cons'):
            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            info = el.find(class_='bgr-product-review-pros')
            if info:
                new_html += '<div style="flex:1; min-width:240px;"><div style="font-weight:bold;">PROS:</div><ul>'
                for it in info.find_all('li'):
                    if it.get_text().strip():
                        new_html += '<li>{}</li>'.format(it.get_text())
                new_html += '</div>'
            info = el.find(class_='bgr-product-review-cons')
            if info:
                new_html += '<div style="flex:1; min-width:240px;"><div style="font-weight:bold;">CONS:</div><ul>'
                for it in info.find_all('li'):
                    new_html += '<li>{}</li>'.format(it.get_text())
                new_html += '</div>'
            new_html += '</div>'
        info = el.find(class_='bgr-product-review-vendors')
        if info and info.table:
            info.table.attrs = {}
            info.table['style'] = 'width:100%;'
            for it in info.table.find_all('th'):
                it['style'] = 'text-align:left;'
            for it in info.find_all('img', class_='vendor-logo'):
                new_el = soup.new_tag('span')
                new_el.string = it['alt'].replace('logo', '').replace('-', ' ').title()
                it.replace_with(new_el)
            new_html += str(info.table)
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='bgr-commerce-block'):
        new_html = '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
        info = el.find(class_='bgr-commerce-info')
        if info:
            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            it = el.find(class_='bgr-commerce-image')
            if it and it.img:
                if it.a:
                    new_html += '<div style="flex:1; min-width:240px;"><a href="{}"><img src="{}" style="width:100%;"/></a></div>'.format(it.a['href'], it.img['src'])
                else:
                    new_html += '<div style="flex:1; min-width:240px;"><img src="{}" style="width:100%;"/></div>'.format(it.img['src'])
            info = el.find(class_='bgr-commerce-details')
            if info:
                new_html += '<div style="flex:1; min-width:240px;">'
                it = info.find('h3')
                if it:
                    new_html += '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(it.get_text())
                it = info.find(class_='sr-only')
                if it:
                    m = re.search(r'[\d\.]+', it.get_text())
                    if m:
                        new_html += '<div style="font-size:2em; font-weight:bold; text-align:center;">'
                        n = float(m.group(0))
                        for i in range(math.floor(n)):
                            new_html += '★'
                        if n % 1 > 0.0:
                            new_html += '½'
                        new_html += '</div>'
                it = info.find(class_='bgr-commerce-description')
                if it:
                    new_html += it.decode_contents()
                new_html += '</div>'
            new_html += '</div>'
        if el.find(class_='bgr-commerce-pros-cons'):
            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            info = el.find(class_='bgr-commerce-pros')
            if info:
                new_html += '<div style="flex:1; min-width:240px;"><div style="font-weight:bold;">PROS:</div><ul>'
                for it in info.find_all('li'):
                    if it.get_text().strip():
                        new_html += '<li>{}</li>'.format(it.get_text())
                new_html += '</div>'
            info = el.find(class_='bgr-commerce-cons')
            if info:
                new_html += '<div style="flex:1; min-width:240px;"><div style="font-weight:bold;">CONS:</div><ul>'
                for it in info.find_all('li'):
                    new_html += '<li>{}</li>'.format(it.get_text())
                new_html += '</div>'
            new_html += '</div>'
        info = el.find(class_='bgr-commerce-buttons')
        if info:
            new_html += '<div style="text-align:center;">'
            for it in info.find_all(class_='bgr-commerce-button'):
                it.attrs = {}
                link = it.a['href']
                it.a.attrs = {}
                it.a['href'] = link
                new_html += str(it)
            new_html += '</div>'
        new_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='bgr-commerce-unit'):
        # https://bgr.com/wp-json/bgr/v1/get_commerce_unit?id=&url=https%3A%2F%2Fwww.amazon.com%2FREOLINK-Security-Detection-Spotlight-Time-Lapse%2Fdp%2FB09873G7X3&title=&label=&price=%2494.99&coupon_code=&coupon_expiry=&image_url=&award=&product_grid=&summary=&description=&post_id=6032026&availability_text=
        if not el.get('data-url'):
            el.decompose()
        else:
            comm_url = 'https://bgr.com/wp-json/bgr/v1/get_commerce_unit?'
            for key, val in el.attrs.items():
                if key != 'class':
                    comm_url += '&{}={}'.format(key.replace('data-', ''), quote_plus(val))
            comm_json = utils.get_url_json(comm_url)
            if comm_json and comm_json.get('data'):
                comm_soup = BeautifulSoup(comm_json['data'], 'html.parser')
                new_html = '<table style="width:100%; border-top:1px solid black; border-bottom:1px solid black; padding:8px;"><tr>'
                it = comm_soup.find(class_='image-container')
                if it:
                    new_html += '<td style="vertical-align:top; width:128px;"><a href="{}"><img src="{}" style="width:100%;"/></a></td>'.format(comm_soup.a['href'], it.img['src'])
                new_html += '<td style="vertical-align:top;">'
                it = comm_soup.find(class_='product-title')
                if it:
                    new_html += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(comm_soup.a['href'], it.get_text())
                new_html += '<div>'
                it = comm_soup.find(class_='product-original-price')
                if it:
                    price = it.get_text()
                else:
                    price = ''
                it = comm_soup.find(class_='product-price')
                if it:
                    if price and it.get_text() != price:
                        new_html += '<div><small style="text-decoration:line-through;">{}</small> {}</div>'.format(price, it.get_text())
                    else:
                        new_html += '<div>{}</div>'.format(it.get_text())
                elif price:
                        new_html += '<div>{}</div>'.format(price)
                it = comm_soup.find(class_='product-buy-button')
                if it:
                    new_html += '<div><a href="{}">{}</a></div>'.format(comm_soup.a['href'], it.get_text())
                new_html += '</div></td></tr></table>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unable to get commerce data from ' + comm_url)

    for el in soup.find_all(class_='case-documents'):
        # https://www.democracydocket.com/cases/indiana-mail-in-voting-restrictions-challenge/
        new_html = ''
        it = el.find(class_='case-documents__heading')
        if it:
            new_html += '<h2>{}</h2>'.format(it.get_text())
        new_html += '<ul>'
        for it in el.find_all(class_='case-documents__item'):
            link = it.find('a', class_='case-documents__item-link')
            span = it.find('span', class_='screen-reader-text')
            if span:
                span.decompose()
            new_html += '<li><span style="font-size:1.5em;">🗎</span> <a href="{}">{}</a></li>'.format(link['href'], it.get_text().strip())
        new_html += '</ul>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='ebook-link-wrapper'):
        new_html = ''
        it = el.find('img')
        if it:
            new_html += '<img src="{}" style="float:left; margin-right:8px; width:128px;"/>'.format(it['src'])
        else:
            new_html += '<img src="{}/image?width=24&height=24&color=none" style="float:left; margin-right:8px;"/>'.format(config.server)
        new_html += '<div style="overflow:hidden;">'
        it = el.find('h3')
        if it:
            new_html += str(it)
        if el.find('ul', class_='ebook-links'):
            new_html += '<ul>'
            for it in el.find_all('a', attrs={"data-book-store": True}):
                new_html += '<li><a href="{}">{}</a></li>'.format(it['href'], it['data-book-store'])
            new_html += '</ul>'
        new_html += '</div><div style="clear:left;"></div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='et-box'):
        el.attrs = {}
        el.name = 'blockquote'
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all(class_='su-box'):
        new_html = '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        content = el.find(class_='su-box-content')
        img_src = ''
        link = ''
        for it in content.find_all():
            img = it.find('img')
            if img:
                img_src = img['src']
                if img.parent and img.parent.name == 'a':
                    link = it['href']
                it.decompose()
                break
        if img_src and link:
            new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><a href="{}"><img style="width:100%;" src="{}"/></a></div>'.format(link, img_src)
        elif img_src:
            new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><img style="width:100%;" src="{}"/></div>'.format(img_src)
        new_html += '<div style="flex:2; min-width:256px;">'
        it = el.find(class_='su-box-title')
        if it and link:
            new_html += '<div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div>'.format(link, it.get_text())
        elif it:
            new_html += '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(it.get_text())
        new_html += '<div>{}</div>'.format(content.decode_contents())
        new_html += '</div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-snopes-fact-check-claim'):
        new_html = '<br/><table style="width:95%; margin-left:auto; margin-right:auto; border-collapse:collapse;">'
        it = el.find(class_='card-header')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><h2 style="margin:0;">{}</h2></td></tr>'.format(it.get_text())
        it = el.find(class_='card-body')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><span style="font-size:1.2em;">{}</span></td></tr>'.format(it.decode_contents())
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-snopes-fact-check-rating'):
        new_html = '<br/><table style="width:95%; margin-left:auto; margin-right:auto; border-collapse:collapse;">'
        it = el.find(class_='card-header')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><h2 style="margin:0;">{}</h2></td></tr>'.format(it.get_text())
        for body in el.find_all(class_='card-body'):
            img = body.find('img')
            if img:
                rating = body.find(class_=re.compile(r'rating-label'))
                if img and rating:
                    new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><table><tr><td><img src="{}" style="width:120px;"/></td><td style="vertical-align:top;"><h2 style="margin:0;">{}</h2>'.format(img['src'], rating.get_text())
                    link = body.find('a')
                    if link:
                        new_html += '<a href="{}">{}</a></td></tr></table></td></tr>'.format(link['href'], link.get_text())
                    else:
                        new_html += '</td></tr></table></td></tr>'
            else:
                it = body.find(class_='media-body')
                if it.span:
                    it.span.attrs = {}
                    it.span.name = 'h3'
                new_html += '<tr><td style="border:1px solid black; padding:0.5em;">{}</td></tr>'.format(it.decode_contents())
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('figure', class_='wp-block-embed'):
        new_html = None
        if 'wp-block-embed-youtube' in el['class']:
            it = el.find('iframe')
            if it:
                if it.get('data-src'):
                    new_html = utils.add_embed(it['data-src'])
                else:
                    new_html = utils.add_embed(it['src'])
            elif el.find(class_='__youtube_prefs__', attrs={"data-facadesrc": True}):
                it = el.find(class_='__youtube_prefs__')
                new_html = utils.add_embed(it['data-facadesrc'])
            elif el.find(class_='lyte-wrapper'):
                # https://hometheaterreview.com/formovie-theater-ust-4k-projector-review/
                it = el.find('meta', attrs={"itemprop": "embedURL"})
                if it:
                    new_html = utils.add_embed(it['content'])
            else:
                it = el.find('lite-youtube')
                if it:
                    new_html = utils.add_embed('https://www.youtube.com/embed/{}'.format(it['videoid']))
        elif 'wp-block-embed-twitter' in el['class']:
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif 'wp-block-embed-instagram' in el['class']:
            it = el.find('blockquote')
            if it:
                new_html = utils.add_embed(it['data-instgrm-permalink'])
            else:
                m = re.search(r'https://www\.instagram\.com/p/[^/]+/', str(el))
                if m:
                    new_html = utils.add_embed(m.group(0))
        elif 'wp-block-embed-tiktok' in el['class']:
            it = el.find('blockquote')
            if it:
                new_html = utils.add_embed(it['cite'])
        elif 'wp-block-embed-facebook' in el['class']:
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif el.find('video'):
            it = el.find('source')
            if it:
                poster = '{}/image?url={}'.format(config.server, quote_plus(it['src']))
                new_html = utils.add_video(it['src'], it['type'], poster)
        elif el.find('iframe'):
            it = el.find('iframe')
            if it:
                if it.get('data-src'):
                    new_html = utils.add_embed(it['data-src'])
                else:
                    new_html = utils.add_embed(it['src'])
        elif el.find('img'):
            add_image(el, None, base_url, site_json)
            continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-embed in ' + item['url'])
            # print(el)

    for el in soup.find_all(class_=re.compile(r'embed-wrap')):
        new_html = ''
        if el.get('data-embedsrc'):
            new_html = utils.add_embed(el['data-embedsrc'])
        else:
            it = el.find('iframe')
            if it:
                if it.get('src'):
                    new_html = utils.add_embed(it['src'])
                elif it.get('data-iframely-url'):
                    new_html = utils.add_embed(it['data-iframely-url'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled {} in {}'.format(el['class'], item['url']))

    for el in soup.find_all(class_='article-embed'):
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled article-embed in ' + item['url'])

    for el in soup.find_all(class_='video-summary-wrap'):
        it = el.find('a', attrs={"rel": "playerjs"})
        if it:
            new_html = utils.add_embed(it['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled video-summary-wrap in ' + item['url'])

    for el in soup.find_all(class_='wp-video'):
        # TODO: caption
        it = el.find('video')
        if it and it.get('poster'):
            poster = it['poster']
        else:
            poster = ''
        it = el.find('source')
        if it:
            new_html = utils.add_video(it['src'], it['type'], poster)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-video in ' + item['url'])

    for el in soup.find_all(class_='jetpack-video-wrapper'):
        new_html = ''
        if el.find(class_=['embed-vimeo', 'embed-youtube']):
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled jetpack-video-wrapper in ' + item['url'])

    for el in soup.find_all(class_='nbcsports-video-wrapper'):
        new_html = ''
        if el.iframe and el.iframe.get('data-mpx-src'):
            page_html = utils.get_url_html(el.iframe['data-mpx-src'])
            page_soup = BeautifulSoup(page_html, 'lxml')
            it = page_soup.find('link', attrs={"type": "application/smil+xml"})
            if it:
                video_src = utils.get_redirect_url(it['href'])
                if re.search('.mp4', video_src, flags=re.I):
                    video_type = 'video/mp4'
                else:
                    video_type = 'application/x-mpegURL'
                it = page_soup.find('meta', attrs={"property": "og:image"})
                if it:
                    poster = it['content']
                else:
                    poster = ''
                it = page_soup.find('meta', attrs={"property": "og:description"})
                if it:
                    caption = it['content']
                else:
                    caption = ''
            new_html = utils.add_video(video_src, video_type, poster, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        if not new_html:
            logger.warning('unhandled nbcsports-video-wrapper in ' + item['url'])

    for el in soup.find_all(class_='epyt-video-wrapper'):
        it = el.find(class_='__youtube_prefs__')
        if it:
            if it.get('data-facadesrc'):
                new_html = utils.add_embed(it['data-facadesrc'])
            else:
                new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled epyt-video-wrapper in ' + item['url'])

    for el in soup.find_all(class_='ami-video-placeholder'):
        it = el.find('script', attrs={"data-type": "s2nScript"})
        if it and it.get('src'):
            if it['src'].startswith('//'):
                src = 'https:' + it['src']
            else:
                src = it['src']
            new_html = utils.add_embed(src)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled ami-video-placeholder')

    for el in soup.find_all('a', class_='story-img-link'):
        if el.get('data-displayinline'):
            new_html = utils.add_embed(el['data-displayinline'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='elementor-element'):
        if el.name == None:
            continue
        new_html = ''
        if 'elementor-widget-video' in el['class']:
            data_json = json.loads(el['data-settings'])
            if data_json['video_type'] == 'youtube':
                new_html = utils.add_embed(data_json['youtube_url'])
        elif 'elementor-widget-image' in el['class']:
            add_image(el, None, base_url, site_json)
            continue
        elif 'elementor-widget-image-box' in el['class']:
            add_image(el, None, base_url, site_json)
            continue
        elif 'elementor-widget-premium-img-gallery' in el['class']:
            data_json = json.loads(el['data-settings'])
            for it in data_json['premium_gallery_img_content']:
                captions = []
                if it.get('premium_gallery_img_name'):
                    captions.append(it['premium_gallery_img_name'])
                if it.get('premium_gallery_img_desc'):
                    captions.append(it['premium_gallery_img_desc'])
                new_html += utils.add_image(it['premium_gallery_img']['url'], ' | '.join(captions))
        elif 'elementor-widget-bdt-custom-gallery' in el['class']:
            for it in el.find_all(class_='bdt-gallery-item'):
                captions = []
                elm = it.find(class_='bdt-gallery-item-title')
                if elm:
                    captions.append(elm.decode_contents().strip())
                elm = it.find(class_='bdt-gallery-item-text')
                if elm:
                    captions.append(elm.decode_contents())
                elm = it.find('a', class_='bdt-gallery-item-link')
                new_html += utils.add_image(elm['href'], ' | '.join(captions))
        elif 'elementor-widget-pp-review-box' in el['class']:
            for it in el.find_all(class_=['pp-review-box-container', 'pp-review-box-overlay', 'pp-review-box-inner', 'pp-review-box-header', 'pp-review-box-content', 'pp-review-pros-cons', 'pp-review-pros', 'pp-review-cons', 'pp-review-summary-wrap']):
                it.unwrap()
            for it in el.find_all(class_=['pp-review-box-subheading', 'pp-review-final-rating-title', 'pp-review-summary-title']):
                it.name = 'h3'
                it.attrs = {}
            it = el.find(class_='pp-review-final-rating')
            if it:
                it.attrs = {}
                it['style'] = 'font-size:3em; font-weight:bold;'
            it = el.find(class_='pp-review-stars')
            if it:
                it.decompose()
            el.name = 'blockquote'
            el.attrs = {}
            el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
            continue
        elif 'elementor-widget-pp-info-box' in el['class']:
            new_html = '<table><tr>'
            it = el.find(class_='pp-info-box')
            if it:
                if it.a and it.img:
                    new_html += '<td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;"/></a></td>'.format(it.a['href'], it.img['src'])
            it = el.find(class_='pp-info-box-content')
            if it:
                for elm in it.find_all(class_=['pp-info-box-title-wrap', 'pp-info-box-title-container', 'pp-info-box-description']):
                    elm.unwrap()
                for elm in it.find_all(class_=['pp-info-box-title', 'pp-info-box-subtitle']):
                    elm.name = 'h3'
                    elm.attrs = {}
                new_html += '<td>' + it.decode_contents() + '</td>'
            new_html += '</tr></table>'
        elif 'elementor-widget-star-rating' in el['class']:
            it = el.find(class_='elementor-star-rating')
            if it:
                new_html = '<div style="font-size:1.2em; font-weight:bold;">CoffeeGeek Rating: <span style="font-size:1.5em;">{}</span></div>'.format(it['title'])
        elif 'elementor-widget-divider' in el['class']:
            new_html = '<hr/>'
        elif 'elementor-widget-author-box' in el['class']:
            el.decompose()
            continue
        elif el.find(class_='gfotoss'):
            el.decompose()
            continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled elementor-element {} in {}'.format(el['class'], item['url']))

    for el in soup.find_all(class_='sketchfab-embed-wrapper'):
        new_html = ''
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled sketchfab-embed-wrapper in ' + item['url'])

    for el in soup.find_all(class_='infogram-embed'):
        if el.get('data-id'):
            new_html = utils.add_embed('https://e.infogram.com/{}?src=embed'.format(el['data-id']))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled infogram-embed in ' + item['url'])

    for el in soup.find_all(class_=['gallery', 'tiled-gallery', 'wp-block-gallery', 'wp-block-jetpack-tiled-gallery', 'article-slideshow', 'wp-block-jetpack-slideshow', 'ess-gallery-container', 'inline-slideshow', 'list-gallery', 'm-carousel', 'multiple-images', 'image-pair', 'undark-image-caption', 'photo-layout', 'rslides', 'banner-grid-wrapper', 'slider-wrapper']):
        if set(['gallery', 'tiled-gallery', 'wp-block-gallery', 'wp-block-jetpack-tiled-gallery']).intersection(el['class']):
            images = None
            if el.find('ul', class_='gallery-wrap'):
                images = el.find_all('li')
                caption = True
            elif 'wp-block-jetpack-tiled-gallery' in el['class']:
                # https://rogersmovienation.com/2023/05/22/movie-review-disney-remakes-the-little-mermaid-but-is-it-music-to-me/
                images = el.find_all(class_='tiled-gallery__item')
                caption = True
            elif 'has-nested-images' in el['class']:
                images = el.find_all('figure')
                caption = True
            else:
                images = el.find_all(class_='gallery-item')
                caption = True
            if not images:
                images = [img for img in el.find_all('img') if (img.get('class') and 'carousel-thumbnail' not in img['class'])]
                caption = False
        elif set(['article-slideshow', 'wp-block-jetpack-slideshow']).intersection(el['class']):
            images = el.find_all('li')
            caption = True
        elif 'ess-gallery-container' in el['class']:
            # https://www.essence.com/entertainment/beyonce-dubai-atlantis-the-royal-grand-reveal-performance/
            images = el.find_all(class_='gallery-slide')
            caption = True
        elif 'inline-slideshow' in el['class']:
            # https://trendeepro.com/like-emily-ratajkowski-im-a-mom-who-takes-my-baby-to-work/
            images = el.find_all(class_='inline-slideshow__slide')
            caption = True
        elif 'list-gallery' in el['class']:
            images = el.find_all(class_='ami-gallery-item')
            caption = True
        elif 'm-carousel' in el['class']:
            # https://www.digitaltrends.com/mobile/oneplus-11-review/
            images = el.find_all('figure', class_='m-carousel--content')
            caption = True
        elif 'multiple-images' in el['class']:
            # https://themarkup.org/news/2023/02/08/how-big-tech-rewrote-the-nations-first-cellphone-repair-law
            images = el.find_all('li', class_='multiple-images__item')
            caption = False
        elif 'image-pair' in el['class']:
            images = el.find_all('figure', class_='image-pair__figure')
            caption = True
        elif 'undark-image-caption' in el['class']:
            # https://undark.org/2023/02/22/how-an-early-warning-radar-could-prevent-future-pandemics/
            images = el.find_all(class_='cell')
            caption = True
        elif 'photo-layout' in el['class']:
            # https://news.harvard.edu/gazette/story/2023/05/inspired-by-mother-bacow-decided-he-wasnt-done-being-a-leader/
            images = el.find_all(class_='photo-layout__image-wrap')
            if not images:
                images = el.find_all(class_='photo-layout__image')
            caption = False
        elif 'rslides' in el['class']:
            # https://www.timesofisrael.com/idf-warns-civilians-to-leave-northern-gaza-as-ground-invasion-looms/
            images = el.find_all('li')
            caption = True
        elif 'banner-grid-wrapper' in el['class']:
            # https://www.audubonart.com/extinct-species-in-audubons-birds-of-america/
            images = el.find_all(class_='img')
            caption = True
        elif 'slider-wrapper' in el['class']:
            # https://www.audubonart.com/the-inclusion-of-foreign-avian-species-in-goulds-birds-of-europe/
            images = el.find_all(class_='img')
            caption = True
        gallery_parent = el.find_parent('div', id=re.compile(r'attachment_\d'))
        if not gallery_parent:
            gallery_parent = el
        n = len(images) - 1
        for i, img in enumerate(images):
            if i < n:
                add_image(img, gallery_parent, base_url, site_json, caption, False, True, i+1)
            else:
                add_image(img, gallery_parent, base_url, site_json, True, False, True, i+1)
            img.decompose()
        gallery_parent.decompose()

    for el in soup.find_all(class_='pbslideshow-wrapper'):
        # https://www.playstationlifestyle.net/2023/01/23/forspoken-review-ps5-worth-playing
        page_html = utils.get_url_html(item['url'])
        page_soup = BeautifulSoup(page_html, 'lxml')
        it = page_soup.find('script', string=re.compile(r'wpQueryVars'))
        if not it:
            logger.warning(r'unable to find wpQueryVars in ' + item['url'])
            continue
        m = re.search(r'query : \'([^\']+)\'', it.string, flags=re.S)
        if not m:
            logger.warning(r'unable to parse wpQueryVars in ' + item['url'])
            continue
        query = m.group(1)
        it = el.find(id=re.compile(r'ngg-gallery-\d+-\d+'))
        if not it:
            logger.warning(r'unhandled pbslideshow-wrapper with no ngg-gallery in ' + item['url'])
            continue
        m = re.search(r'ngg-gallery-(\d+)-(\d+)', it['id'])
        slideshow_id = m.group(1)
        page_html = utils.get_url_html('{}/index.php?action=get_slideshow&slideshow_id={}&template=desktopview&imagetag=&query={}'.format(base_url, slideshow_id, quote_plus(query)))
        if not page_html:
            logger.warning('unable to get_slideshow for ' + item['url'])
            continue
        utils.write_file(page_html, './debug/slideshow.html')
        page_soup = BeautifulSoup(page_html, 'html.parser')
        images = page_soup.find_all(class_='pbslideshow-slider-item')
        desc = page_soup.find_all(class_='pbslideshow-description-inner')
        new_html = '<h2>Gallery</h2>'
        for i, it in enumerate(images):
            if desc[i].get_text().strip():
                new_html += utils.add_image(resize_image(it['data-pbslazyurl'], site_json), desc=str(desc[i]))
            else:
                new_html += utils.add_image(resize_image(it['data-pbslazyurl'], site_json))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='foogallery'):
        # https://techaeris.com/2022/12/20/steelseries-aerox-5-wireless-review-stellar-mouse-varying-battery-life/
        for it in el.find_all(class_='fg-item'):
            new_html = ''
            img = it.find('a', class_='fg-thumb')
            if img:
                img_src = img['href']
                if img_src.startswith('/'):
                    img_src = base_url + img_src
                if img.get('data-caption-title'):
                    caption = img['data-caption-title']
                elif it.find(class_='fg-caption-title'):
                    caption = it.find(class_='fg-caption-title').get_text().strip()
                else:
                    caption = ''
                new_html = utils.add_image(resize_image(img_src, site_json), caption)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_before(new_el)
            else:
                logger.warning('unhandled article-slideshow image')
        el.decompose()

    for el in soup.find_all(class_='photowrap'):
        new_html = ''
        it = el.find(attrs={"data-photo-id": True})
        if it:
            media_json = utils.get_url_json('{}{}/{}'.format(site_json['wpjson_path'], site_json['posts_path'].replace('posts', 'media'), it['data-photo-id']))
            if media_json:
                img_src = utils.closest_dict(media_json['media_details']['sizes'], 'width', 1200)
                if media_json.get('caption') and media_json['caption'].get('rendered'):
                    media_soup = BeautifulSoup(media_json['caption']['rendered'], 'html.parser')
                    if media_soup.p:
                        caption = media_soup.p.decode_contents()
                    else:
                        caption = media_soup.get_text()
                else:
                    caption = ''
                new_html += utils.add_image(img_src['source_url'], caption)
        else:
            # https://hudexplorernews.org/2614/multimedia/boys-cross-country-meet-in-wooster/
            it = el.find(attrs={"data-photo-ids": True})
            if it:
                for media_id in it['data-photo-ids'].split(','):
                    #print('{}{}/{}'.format(site_json['wpjson_path'], site_json['posts_path'].replace('posts', 'media'), media_id.strip()))
                    media_json = utils.get_url_json('{}{}/{}'.format(site_json['wpjson_path'], site_json['posts_path'].replace('posts', 'media'), media_id.strip()))
                    if media_json:
                        img_src = utils.closest_dict(media_json['media_details']['sizes'].values(), 'width', 1200)
                        if media_json.get('caption') and media_json['caption'].get('rendered'):
                            media_soup = BeautifulSoup(media_json['caption']['rendered'], 'html.parser')
                            if media_soup.p:
                                caption = media_soup.p.decode_contents()
                            else:
                                caption = media_soup.get_text()
                        else:
                            caption = ''
                        new_html += utils.add_image(img_src['source_url'], caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_before(new_el)
            el.decompose()
        else:
            logger.warning('unhandled photowrap')

    for el in soup.find_all(class_=re.compile(r'bp-embedded-image|c-figure|captioned-image-container|custom-image-block|entry-image|featured-media-img|gb-block-image|img-wrap|pom-image-wrap|post-content-image|block-coreImage|wp-block-image|wp-block-ups-image|wp-caption|wp-image-\d+|wp-block-media|img-container')):
        add_image(el, None, base_url, site_json)

    for el in soup.find_all('figure', id=re.compile(r'media-\d+')):
        add_image(el, None, base_url, site_json)

    for el in soup.find_all('div', class_='cover-image-wrapper'):
        # https://www.growbyginkgo.com/2024/01/09/getting-under-the-skin/
        it = el.find('video')
        if it and it.get('src'):
            new_html = utils.add_video(it['src'], 'video/mp4')
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_before(new_el)
            el.decompose()
        else:
            logger.warning('unhandled cover-image-wrapper in ' + item['url'])

    for el in soup.find_all('div', class_='box'):
        if el.find(class_='box-image'):
            add_image(el, None, base_url, site_json)

    for el in soup.find_all('div', id=re.compile(r'image_\d+')):
        add_image(el, None, base_url, site_json)

    for el in soup.find_all('figure', attrs={}):
        if el.attrs == {}:
            add_image(el, None, base_url, site_json)

    #for el in soup.find_all('img', class_='post-image'):
    for el in soup.find_all(lambda tag: tag.name == 'img' and
            (('class' in tag.attrs and 'post-image' in tag.attrs['class']) or
             ('alt' in tag.attrs) or ('width' in tag.attrs) or ('decoding' in tag.attrs))):
        if el.parent and el.parent.name == 'a' and el['src'].startswith('https://secure.livedownloads.com/images/shows/'):
            el.parent.wrap(BeautifulSoup().new_tag('div'))
            continue
        elif el.parent and el.parent.name == 'a' and el.parent.get('class') and 'app-icon' in el.parent['class']:
            continue
        elif el.get('class'):
            if 'ql-img-inline-formula' in el['class'] or 'latex' in el['class']:
                # https://www.logicmatters.net/2023/02/15/does-mathematics-need-a-philosophy/
                if el['src'].startswith('data:'):
                    el['src'] = el['data-src']
                continue
        add_image(el, None, base_url, site_json)

    for el in soup.find_all(class_='media-wrapper'):
        # Used on macstories.net
        new_html = ''
        if 'subscribe-podcast-cta' in el['class']:
            el.decompose()
        elif 'audio-player' in el['class']:
            it = el.find('source')
            if it:
                new_html = '<div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Play</a></span></div>'.format(it['src'], config.server)
        elif el.find(class_='image-caption'):
            img_src = el.img['src']
            if img_src.startswith('/'):
                img_src = base_url + img_src
            it = el.find(class_='image-caption')
            if it:
                caption = it.get_text().strip()
            else:
                caption = ''
            new_html = utils.add_image(resize_image(img_src, site_json), caption)
        elif el.find('iframe', class_='youtube-player'):
            new_html = utils.add_embed(el.iframe['src'])
        elif el.find('iframe', attrs={"src": re.compile(r'podcasts\.apple\.com')}):
            new_html = utils.add_embed(el.iframe['src'])
        else:
            logger.warning('unhandled media-wrapper class {}'.format(el['class']))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='g-block-wrapper'):
        # https://golf.com/gear/golf-balls/callaway-ball-plant-chicopee-learned/
        new_html = ''
        it = el.find('parone-video-block')
        if it:
            video_url = 'https://lambda.parone.app/prod/can-play?c=undefined&ck={}&feed=63-all-system-videos&fingerprint={}'.format(it['content-key'], random.randint(1000000000, 9999999999))
            video_json = utils.get_url_json(video_url)
            if video_json:
                new_html = utils.add_video(video_json['url'], 'application/x-mpegURL', video_json['thumbnail'], video_json['title'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled g-block-wrapper in ' + item['url'])

    for el in soup.find_all(class_='video-player'):
        # https://stratechery.com/2022/microsoft-full-circle/
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.get('align'):
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled video-player in ' + item['url'])

    for el in soup.find_all(class_='video-player-container'):
        # https://www.investors.com/news/technology/amazon-stock-amzn-q3-earnings-2023/
        new_html = ''
        it = el.find(class_='shortcode-video')
        if it:
            if it.get('jw-video-key'):
                new_html = utils.add_embed('https://cdn.jwplayer.com/players/{}-.js'.format(it['jw-video-key']))
            elif it.get('vid-url'):
                if '.mp4' in it['vid-url']:
                    video_type = 'video/mp4'
                else:
                    video_type = 'application/x-mpegURL'
                new_html = utils.add_video(it['vid-url'], video_type, it.get('vid-image'), it.get('vid-name'))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'span':
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled video-player-container in ' + item['url'])

    for el in soup.find_all(class_='wp-block-video'):
        video_src = ''
        if el.video:
            video_src = el.video.get('src')
            poster = el.video.get('poster')
            if not video_src:
                if el.video.source:
                    video_src = el.video.source['src']
        if video_src:
            if re.search(r'\.mp4', video_src) or re.search(r'\.mov', video_src):
                video_type = 'video/mp4'
            elif re.search(r'\.webm', video_src):
                video_type = 'video/webm'
            elif re.search(r'\.m3u8', video_src):
                video_type = 'application/x-mpegURL'
            else:
                logger.warning('unhandled video type for {} in {}'.format(video_src, item['url']))
                video_container = av.open(video_src)
                if 'mp4' in video_container.format.extensions:
                    video_type = 'video/mp4'
                elif 'webm' in video_container.format.extensions:
                    video_type = 'video/webm'
                else:
                    video_type = 'application/x-mpegURL'
                video_container.close()
            if not poster:
                if video_type == 'video/mp4':
                    poster = '{}/image?url={}&width=1000'.format(config.server, quote_plus(video_src))
                else:
                    poster = '{}/image?width=1000&height=563'.format(config.server)
            if el.figcaption:
                caption = el.figcaption.decode_contents()
            else:
                caption = ''
            new_el = BeautifulSoup(utils.add_video(video_src, video_type, poster, caption), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-video in ' + item['url'])

    for el in soup.find_all(class_=['wp-block-audio', 'wp-audio-shortcode']):
        audio_src = ''
        if el.name == 'audio':
            audio = el
        else:
            audio = el.find('audio')
        if audio:
            if audio.get('src'):
                audio_src = audio['src']
            else:
                it = el.find('source')
                if it:
                    audio_src = it['src']
        if audio_src:
            it = el.find(class_='wp-element-caption')
            if it:
                caption = it.get_text()
            else:
                caption = 'Play'
            new_html = '<div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">{2}</a></span></div>'.format(audio_src, config.server, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-audio in ' + item['url'])

    for el in soup.find_all(class_='podcast'):
        # https://www.wired.com/author/geeks-guide-to-the-galaxy/
        poster = '{}/image?&width=256&overlay=audio'.format(config.server)
        it = el.find('img')
        if it:
            poster += '&url=' + quote_plus(it['src'])
        it = el.find('a', href=re.compile(r'\.mp3'))
        if it:
            audio_src = utils.get_redirect_url(it['href'])
        else:
            audio_src = item['url']
        it = el.find('h4')
        if it:
            title = '<h3>{}</h3>'.format(it.get_text())
        else:
            title = ''
        new_html = '<div style="text-align:center;">{}<a href="{}"><img src="{}"/></a></div>'.format(title, audio_src, poster)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='embed-youtube'):
        new_html = ''
        if el.iframe:
            if el.iframe.get('src'):
                new_html = utils.add_embed(el.iframe['src'])
            elif el.iframe.get('data-src'):
                new_html = utils.add_embed(el.iframe['data-src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embed-youtube in ' + item['url'])

    for el in soup.find_all(class_='video-container'):
        new_html = ''
        if el.find(class_='js-video') or 'pmYTPlayerContainer' in el['class']:
            new_html = utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(el['id']))
        else:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled video-container in ' + item['url'])

    for el in soup.find_all(class_='jwplayer_placeholder'):
        new_html = ''
        it = el.find(id=re.compile(r'jwplayer_'))
        if it:
            m = re.search(r'jwplayer_([^_]+)_([^_]+)', it['id'])
            if m:
                new_html = utils.add_embed('https://cdn.jwplayer.com/players/{}-{}.js'.format(m.group(1), m.group(2)))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled video-container in ' + item['url'])

    for el in soup.find_all(class_='dtvideos-container'):
        if el.get('data-provider') and el['data-provider'] == 'youtube':
            it = el.find(class_='h-embedded-video')
            if it:
                new_el = BeautifulSoup(utils.add_embed(it['data-url']), 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhanlded youtube dtvideo-container in ' + item['url'])
        else:
            logger.warning('unhandled dtvideos-container in ' + item['url'])

    for el in soup.find_all(attrs={"data-embed-type": "Brightcove"}) + soup.find_all(class_='brightcove'):
        it = el.find('video')
        if it:
            new_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(it['data-account'], it['data-player'], it['data-video-id']))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled Brightcove embed in ' + item['url'])

    for el in soup.find_all('video', class_='video-js'):
        new_html = ''
        if el.get('data-player'):
            new_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(el['data-account'], el['data-player'], el['data-video-id']))
        elif el.get('data-opts'):
            data_opts = json.loads(el['data-opts'])
            source = utils.closest_dict(data_opts['plugins']['sources']['renditions'], 'frameHeight', 480)
            if source['videoContainer'] == 'MP4':
                video_type = 'video/mp4'
            else:
                video_type = 'application/x-mpegURL'
            new_html = utils.add_video(source['url'], video_type, data_opts['poster'], data_opts['title'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el_parent = el
            while el_parent.parent.parent:
                el_parent = el_parent.parent
            el_parent.insert_after(new_el)
            el_parent.decompose()
        else:
            logger.warning('unhandled video-js embed in ' + item['url'])

    for el in soup.find_all(class_='blogstyle__iframe'):
        new_html = ''
        it = el.find('iframe')
        if it:
            if it.get('src'):
                new_html = utils.add_embed(it['src'])
            elif it.get('data-src'):
                new_html = utils.add_embed(it['data-src'])
            else:
                logger.warning('unknown iframe src in ' + item['url'])
        else:
            it = el.find(class_='twitter-tweet')
            if it:
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled blogstyle__iframe in ' + item['url'])

    for el in soup.find_all('iframe'):
        if el.name == None:
            continue
        new_html = ''
        el_parent = el
        if el.get('src') and 'dataviz.theanalyst.com' in el['src']:
            new_html = utils.add_image('{}/screenshot?url={}&locator=body&networkidle=1'.format(config.server, quote_plus(el['src'])), link=el['src'])
        else:
            it = el.find_parent(class_='embed')
            if it:
                el_parent = it
            else:
                for it in reversed(el.find_parents()):
                    if it.name == 'p':
                        has_str = False
                        for c in it.contents:
                            if isinstance(c, bs4.element.NavigableString):
                                has_str = True
                        if not has_str:
                            el_parent = it
                            break
                    elif not it.find('p'):
                        el_parent = it
                        break

            if el.get('src'):
                src = el['src']
            elif el.get('data-src'):
                src = el['data-src']
            else:
                src = ''
            if src:
                if not re.search(r'amazon-adsystem\.com', src):
                    new_html = utils.add_embed(src)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el_parent.insert_after(new_el)
            el_parent.decompose()
        else:
            logger.warning('unhandled iframe in ' + item['url'])

    for el in soup.find_all(class_=['twitter-tweet', 'twitter-video', 'twitter-quote']):
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(attrs={"data-initial-classes": "twitter-tweet"}):
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='tiktok-embed'):
        new_el = BeautifulSoup(utils.add_embed(el['cite']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(id=re.compile(r'buzzsprout-player-\d+')):
        it = soup.find('script', src=re.compile(el['id']))
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='pull-number'):
        # https://themarkup.org/privacy/2023/02/16/forget-milk-and-eggs-supermarkets-are-having-a-fire-sale-on-data-about-you
        it = el.find(class_='pull-number__content')
        if it:
            author = el.find(class_='pull-number__source')
            if author:
                new_html = utils.add_blockquote(it.decode_contents() + '<small>{}</small>'.format(author.decode_contents()))
            else:
                new_html = utils.add_blockquote(it.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled pull-number in ' + item['url'])

    for el in soup.find_all(class_='quote'):
        it = el.find(class_='quote__text')
        if it:
            # TODO: citation/author?
            new_html = utils.add_pullquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(id='quote-block'):
        # https://www.mobileworldlive.com/samsung/samsung-unpacks-galaxy-s24-packed-with-google-ai/
        for it in el.find_all('img'):
            it.decompose()
        captions = []
        for it in el.find_all('span', class_='text-xs'):
            captions.append(it.get_text().strip())
            it.decompose()
        new_html = utils.add_pullquote(el.div.decode_contents(), ' | '.join(captions))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_=['pullquote', 'wp-block-pullquote', 'simplePullQuote', 'undark-pull-quote']):
        if el.blockquote:
            el.blockquote.unwrap()
        it = el.find('cite')
        if it:
            author = it.get_text()
            it.decompose()
        else:
            author = ''
        it = el.find(class_='soundcite')
        if it:
            it.decompose()
        it = el.find(class_='blockquote-text')
        if it:
            new_html = utils.add_pullquote(it.decode_contents(), author)
        else:
            it = el.find(class_='undark-quote')
            if it:
                new_html = utils.add_pullquote(it.get_text().strip(), author)
            else:
                new_html = utils.add_pullquote(el.decode_contents(), author)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('blockquote'):
        if el.name == None or re.search(r'^Embedded content from', el.get_text()):
            # Likely a nested blockquote which won't get styled
            continue
        new_html = ''
        if el.get('class'):
            if 'instagram-media' in el['class']:
                new_html = utils.add_embed(el['data-instgrm-permalink'])
            elif 'reddit-embed-bq' in el['class']:
                it = el.find('a')
                if it:
                    new_html = utils.add_embed(it['href'])
            elif el.find('code') and not el.find('p'):
                el.attrs = {}
                el.name = 'pre'
                continue
            elif 'pull-right' in el['class'] or 'pull-left' in el['class'] or 'pull-center' in el['class']:
                quote = el.decode_contents().strip()
                new_html = utils.add_pullquote(quote)
            elif 'wp-block-quote' in el['class'] or 'wp-block-pullquote' in el['class'] or 'puget-blockquote' in el['class']:
                it = el.find('cite')
                if it:
                    author = it.decode_contents().strip()
                    it.decompose()
                else:
                    author = ''
                it = el.find(class_='blockquote-text')
                if it:
                    quote = it.decode_contents().strip()
                else:
                    quote = el.decode_contents().strip()
                if quote:
                    if author or 'wp-block-pullquote' in el['class']:
                        new_html = utils.add_pullquote(quote, author) + '<div>&nbsp;</div>'
                    else:
                        new_html = utils.add_blockquote(quote)
                else:
                    new_html = '<div>&nbsp;</div>'
        if not new_html:
            if el.get('id') and re.search(r'blockquote\d', el['id']):
                new_html = utils.add_blockquote(el.decode_contents())
            else:
                it = el.find(class_='quote-author')
                if it:
                    author = it.get_text().strip()
                    if author == 'by':
                        author = ''
                    it.decompose()
                    new_html = utils.add_pullquote(el.decode_contents(), author)
                else:
                    if el.get_text().strip():
                        new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_=re.compile(r'textbox\d')):
        el.name = 'blockquote'
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all(class_='wp-block-file'):
        # https://scalawagmagazine.org/2023/06/new-orleans-musicians-clinic/
        if el.object:
            new_html = '<p style="line-height:2em;"><span style="font-size:1.5em; vertical-align:middle;">🗎</span>&nbsp;<span style="vertical-align:middle;"><a href="{}">{}</a></span></p>'.format(el.object['data'], el.object['aria-label'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        elif el.find(class_='wp-block-file__button'):
            it = el.find(class_='wp-block-file__button')
            it.string = ' ⭳ '
        else:
            logger.warning('unhandled wp-block-file in ' + item['url'])

    for el in soup.find_all(class_='wp-block-prc-block-collapsible'):
        new_html = ''
        it = el.find(class_='wp-block-prc-block-collapsible__title')
        if it:
            new_html += '<h4>{}</h4>'.format(it.get_text().strip())
        it = el.find(class_='wp-block-prc-block-collapsible__content')
        if it:
            new_html += it.decode_contents()
        new_el = BeautifulSoup(utils.add_blockquote(new_html), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='box'):
        if 'shadow' in el['class']:
            it = el.find(class_='tieicon-boxicon')
            if it:
                it.decompose()
            it = el.find(class_='box-inner-block')
            if it:
                new_html = utils.add_blockquote(it.decode_contents())
            else:
                new_html = utils.add_blockquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('p', class_='has-background'):
        new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    # wp-block-code
    for el in soup.find_all('pre'):
        #if el.find('code') or (el.get('class') and re.search(r'bash', ', '.join(el['class']))) or re.search(r'^$|sudo|', el.get_text().strip()):
        el.attrs = {}
        el['style'] = 'padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;'
        it = el.find_parent('div', class_='wp-block-syntaxhighlighter-code')
        if it:
            it.unwrap()

    for el in soup.find_all(class_='codecolorer-container'):
        el.name = 'pre'
        el.attrs = {}
        el['style'] = 'padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;'
        it = el.find(class_='codecolorer')
        it.name = 'code'

    for el in soup.find_all('code'):
        if el.parent:
            el['style'] = 'background:#F2F2F2;'
        else:
            new_html = '<pre style="padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;">{}</pre>'.format(str(el))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='article-pull-quote'):
        quote = el.find(class_='text')
        if quote:
            it = el.find(class_='author')
            if it:
                author = it.get_text()
            else:
                author = ''
            new_el = BeautifulSoup(utils.add_pullquote(quote.decode_contents(), author), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled article-pull-quote')

    for el in soup.find_all(class_='media-element'):
        it = el.find('img', class_='media-element-image')
        if it:
            new_html = '<table><tr><td style="width:128px;"><img src="{}" style="width:100%;"></td><td>'.format(it['src'])
            desc = el.find(class_='media-element-description')
            if desc:
                it = desc.find(class_='title')
                if it:
                    it.name = 'h4'
                    it.attrs = {}
                    it['style'] = 'margin-top:0; margin-bottom:0.5em;'
                desc = desc.decode_contents()
                desc = re.sub(r'</p>\s*<p>', '<br/><br/>', desc)
                desc = re.sub(r'<p>|</p>', '', desc)
                new_html += desc
            new_html += '</td></tr></table>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled media-element')

    for el in soup.find_all(class_='bottom-line-module'):
        it = el.find(class_='module-title')
        if it:
            it.name = 'h4'
            it.attrs = {}
        el.name = 'blockquote'
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all(class_='is-content-justification-center'):
        el.attrs = {}
        el['style'] = 'text-align:center;'

    for el in soup.find_all('a', href=re.compile(r'^/')):
        el['href'] = base_url + el['href']

    for el in soup.find_all('img', src=re.compile(r'^/')):
        el['src'] = base_url + el['src']

    for el in soup.find_all('a', href=re.compile(r'go\.redirectingat\.com/')):
        el['href'] = utils.get_redirect_url(el['href'])

    for el in soup.find_all(class_='product-link'):
        href = utils.get_redirect_url(el['href'])
        el.attrs = {}
        el['href'] = href

    for el in soup.find_all(class_='wp-block-product-widget-block'):
        if el.find(id='mentioned-in-this-article'):
            el.decompose()

    for el in soup.find_all('script', attrs={"src": re.compile(r'datawrapper\.dwcdn\.net')}):
        if el.parent and el.parent.name == 'div':
            m = re.search(r'https://datawrapper\.dwcdn\.net\/[^\/]+', el['src'])
            new_html = utils.add_embed(m.group(0))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.parent.insert_after(new_el)
            el.parent.decompose()

    for el in soup.find_all(['aside', 'ins', 'script', 'style']):
        el.decompose()

    if not item.get('_image'):
        el = soup.find('img')
        if el:
            item['_image'] = el['src']

    content_html = re.sub(r'</(figure|table)>\s*<(div|figure|table|/li)', r'</\1><div>&nbsp;</div><\2', str(soup))
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[-1] == 'embed':
        del paths[-1]
        args['embed'] = True

    page_soup = None
    post = None
    posts_path = ''
    post_url = ''
    if site_json.get('posts_path'):
        if isinstance(site_json['posts_path'], str):
            posts_path = site_json['posts_path']
        elif isinstance(site_json['posts_path'], dict):
            key = set(paths).intersection(site_json['posts_path'].keys())
            if key:
                posts_path = site_json['posts_path'][list(key)[0]]
            else:
                for key, val in site_json['posts_path'].items():
                    for path in paths:
                        if key in path:
                            posts_path = val
                            break
                if not posts_path:
                    posts_path = site_json['posts_path']['default']

        if site_json['wpjson_path'].startswith('/'):
            wpjson_path = '{}://{}{}'.format(split_url.scheme, split_url.netloc, site_json['wpjson_path'])
        else:
            wpjson_path = site_json['wpjson_path']

        # Try to determine the post id or slug from the path
        if site_json.get('slug'):
            post_url = '{}{}?slug={}'.format(wpjson_path, posts_path, paths[site_json['slug']])
            #print(post_url)
            post = utils.get_url_json(post_url)
        else:
            for it in paths:
                if it.isnumeric() and len(it) > 4:
                    post_url = '{}{}/{}'.format(wpjson_path, posts_path, it)
                elif 'no_slug' not in args and '-' in it and not (site_json.get('exclude_slugs') and it in site_json['exclude_slugs']):
                    slug = it.split('.')[0]
                    m = re.search(r'-(\d{5,}$)', slug)
                    if m and 'www.thedailymash.co.uk' in url:
                        post_url = '{}{}/{}'.format(wpjson_path, posts_path, m.group(1)[8:])
                    elif m and not (len(m.group(1)) == 8 and m.group(1).startswith('202')):
                        post_url = '{}{}/{}'.format(wpjson_path, posts_path, m.group(1))
                    else:
                        post_url = '{}{}?slug={}'.format(wpjson_path, posts_path, slug)
                else:
                    continue
                post = utils.get_url_json(post_url)
                if post:
                    break
        if post:
            if isinstance(post, list):
                return get_post_content(post[0], args, site_json, page_soup, save_debug)
            else:
                return get_post_content(post, args, site_json, page_soup, save_debug)

    # Look for the post id in the page
    page_html = utils.get_url_html(url)
    if page_html:
        if save_debug:
            utils.write_file(page_html, './debug/debug.html')
        page_soup = BeautifulSoup(page_html, 'html.parser')
        el = page_soup.find('link', attrs={"rel": "alternate", "type": "application/json", "href": re.compile(r'wp-json')})
        if el:
            post_url = el['href']
        else:
            el = page_soup.find('link', attrs={"rel": "shortlink"})
            if el:
                query = parse_qs(urlsplit(el['href']).query)
                if query.get('p'):
                    post_url = '{}{}/{}'.format(wpjson_path, posts_path, query['p'][0])
        if not post_url:
            el = page_soup.find(id=re.compile(r'post-\d+'))
            if el:
                m = re.search(r'post-(\d+)', el['id'])
                if m:
                    post_url = '{}{}/{}'.format(wpjson_path, posts_path, m.group(1))
            else:
                el = page_soup.find(class_=re.compile(r'postid-\d+'))
                if el:
                    m = re.search(r'postid-(\d+)', ' '.join(el['class']))
                    if m:
                        post_url = '{}{}/{}'.format(wpjson_path, posts_path, m.group(1))
    if not post_url:
        logger.warning('unable to determine wp-json post url in ' + url)
        return None
    post = utils.get_url_json(post_url)
    if not post:
        return None
    return get_post_content(post, args, site_json, page_soup, save_debug)


def find_post_url(page_soup, wpjson_path):
    post_id = ''
    post_url = ''
    # Find the direct wp-json link
    el = page_soup.find('link', attrs={"rel": "alternate", "type": "application/json", "href": re.compile(r'wp-json')})
    if el:
        post_url = el['href']
        m = re.search(r'/(\d+)', post_url)
        if m:
            post_id = m.group(1)
    else:
        # The shortlink is generally of the form: https://www.example.com?p=post_id
        el = page_soup.find('link', attrs={"rel": "shortlink"})
        if el:
            query = parse_qs(urlsplit(el['href']).query)
            if query.get('p'):
                post_id = query['p'][0]
                post_url = '{}/{}'.format(wpjson_path, post_id)
    if not post_url:
        # Sometimes the post id is sometimes in the id/class of the article/content section
        el = page_soup.find(id=re.compile(r'post-\d+'))
        if el:
            m = re.search(r'post-(\d+)', el['id'])
            if m:
                post_id = m.group(1)
                post_url = '{}/{}'.format(wpjson_path, post_id)
        else:
            el = page_soup.find(class_=re.compile(r'postid-\d+'))
            if el:
                m = re.search(r'postid-(\d+)', ' '.join(el['class']))
                if m:
                    post_id = m.group(1)
                    post_url = '{}/{}'.format(wpjson_path, post_id)
            else:
                m = re.search(r'"articleId","(\d+)"', str(page_soup))
                if m:
                    if m:
                        post_id = m.group(1)
                        post_url = '{}/{}'.format(wpjson_path, post_id)
    return post_url, post_id


def get_content_v2(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[-1] == 'embed':
        del paths[-1]
        args['embed'] = True

    page_soup = None
    if not page_soup and (site_json.get('content') or site_json.get('author') or site_json.get('lede_img') or site_json.get('lede_video') or site_json.get('title')):
        page_html = utils.get_url_html(url)
        if page_html:
            if save_debug:
                utils.write_file(page_html, './debug/debug.html')
            page_soup = BeautifulSoup(page_html, 'lxml')

    post_id = ''
    wp_post = None
    yoast_json = None
    ld_json = []
    if site_json.get('wpjson_path'):
        if site_json['wpjson_path'].startswith('/'):
            wpjson_path = '{}://{}{}'.format(split_url.scheme, split_url.netloc, site_json['wpjson_path'])
        else:
            wpjson_path = site_json['wpjson_path']
        if isinstance(site_json['posts_path'], str):
            wpjson_path += site_json['posts_path']
        elif isinstance(site_json['posts_path'], dict):
            key = set(paths).intersection(site_json['posts_path'].keys())
            if key:
                wpjson_path += site_json['posts_path'][list(key)[0]]
            else:
                wpjson_path += site_json['posts_path']['default']

        if page_soup:
            post_url, post_id = find_post_url(page_soup, wpjson_path)
            print(post_id)
            if post_url:
                wp_post = utils.get_url_json(post_url)

        if not wp_post:
            # Try to determine the post id or slug from the path
            # 1. Try to determine the post id number either as a separate path or as part of the slug (exclude possible date values: YYYY, MM, DD)
            # 2. Use the slug - generally has several dashes
            for it in paths:
                wp_post = None
                if it.isnumeric() and len(it) > 4:
                    # Try number as the post id (exclude possible date values: YYYY, MM, DD)
                    post_url = '{}/{}'.format(wpjson_path, it)
                    wp_post = utils.get_url_json(post_url)
                if 'no_slug' not in args and '-' in it and not (site_json.get('exclude_slugs') and it in site_json['exclude_slugs']):
                    # Try path as slug
                    slug = it.split('.')[0]
                    m = re.search(r'-(\d{5,}$)', slug)
                    if m and not (len(m.group(1)) == 8 and m.group(1).startswith('202')):
                        # Check if it contains the post id
                        post_url = '{}/{}'.format(wpjson_path, m.group(1))
                        wp_post = utils.get_url_json(post_url)
                    if not wp_post:
                        post_url = '{}?slug={}'.format(wpjson_path, slug)
                        wp_post = utils.get_url_json(post_url)
                else:
                    continue
                if wp_post:
                    # Finding by slug returns a list of matches
                    if isinstance(wp_post, list):
                        wp_post = wp_post[0]
                    break

            if not wp_post and not page_soup:
                page_html = utils.get_url_html(url)
                if page_html:
                    if save_debug:
                        utils.write_file(page_html, './debug/debug.html')
                    page_soup = BeautifulSoup(page_html, 'html.parser')
                    post_url, post_id = find_post_url(page_soup, wpjson_path)
                    if post_url:
                        wp_post = utils.get_url_json(post_url)

        if not wp_post:
            logger.warning('unable to get wp-json post data in ' + url)
            return None

        if save_debug:
            utils.write_file(wp_post, './debug/debug.json')

        if wp_post.get('yoast_head_json') and wp_post['yoast_head_json'].get('schema'):
            yoast_json = wp_post['yoast_head_json']['schema']
        elif wp_post.get('yoast_head'):
            soup = BeautifulSoup(wp_post['yoast_head'], 'html.parser')
            el = soup.find('script', class_='yoast-schema-graph')
            if el:
                yoast_json = json.loads(el.string)
        if yoast_json:
            if save_debug:
                utils.write_file(yoast_json, './debug/yoast.json')
            if yoast_json.get('schema') and yoast_json['schema'].get('@graph'):
                ld_json = yoast_json['schema']['@graph']

    meta_json = []
    oembed_json = None
    if page_soup:
        for el in page_soup.find_all('meta'):
            if el.get('property'):
                key = el['property']
            elif el.get('name'):
                key = el['name']
            else:
                continue
            if meta_json.get(key):
                if isinstance(meta_json[key], str):
                    if meta_json[key] != el['content']:
                        val = meta_json[key]
                        meta_json[key] = []
                        meta_json[key].append(val)
                if el['content'] not in meta_json[key]:
                    meta_json[key].append(el['content'])
            else:
                meta_json[key] = el['content']
        if save_debug:
            utils.write_file(meta_json, './debug/meta.json')

        if not ld_json:
            for el in page_soup.find_all('script', attrs={"type": "application/ld+json"}):
                try:
                    ld = json.loads(el.string)
                    if isinstance(ld, list):
                        for it in ld:
                            if it.get('@graph'):
                                ld_json += it['@graph'].copy()
                            elif it.get('@type'):
                                ld_json.append(it)
                    elif isinstance(ld, dict):
                        if ld.get('@graph'):
                            ld_json += ld['@graph'].copy()
                        elif ld.get('@type'):
                            ld_json.append(ld)
                except:
                    logger.warning('unable to convert ld+json in ' + url)
                    pass

        el = soup.find('link', attrs={"rel": "alternative", "type": "application/json+oembed"})
        if el:
            oembed_json = utils.get_url_json(el['href'])

    ld_page = None
    ld_article = None
    ld_people = []
    ld_images = []
    if ld_json:
        if save_debug:
            utils.write_file(ld_json, './debug/ld_json.json')

        for ld in ld_json:
            if isinstance(ld, dict):
                it = ld
                if not it.get('@type'):
                    continue
                if isinstance(it['@type'], str):
                    if it['@type'] == 'WebPage':
                        ld_page = it
                    elif 'Article' in it['@type']:
                        ld_article = it
                    elif it['@type'] == 'Product' and it.get('Review'):
                        ld_article = it['Review']
                    elif it['@type'] == 'Person':
                        ld_people.append(it)
                    elif it['@type'] == 'ImageObject':
                        ld_images.append(it)
                elif isinstance(it['@type'], list):
                    if 'WebPage' in it['@type']:
                        ld_page = it
                    elif re.search(r'Article', '|'.join(it['@type'])):
                        ld_article = it
            elif isinstance(ld, list):
                for it in ld:
                    if not it.get('@type'):
                        continue
                    if isinstance(it['@type'], str):
                        if it['@type'] == 'WebPage':
                            ld_page = it
                        elif 'Article' in it['@type']:
                            ld_article = it
                        elif it['@type'] == 'Product' and it.get('Review'):
                            ld_article = it['Review']
                        elif it['@type'] == 'Person':
                            ld_people.append(it)
                        elif it['@type'] == 'ImageObject':
                            ld_images.append(it)
                    elif isinstance(it['@type'], list):
                        if 'WebPage' in it['@type']:
                            ld_page = it
                        elif re.search(r'Article', '|'.join(it['@type'])):
                            ld_article = it

        if not ld_article and ld_page:
            ld_article = ld_page

    item = {}
    if wp_post:
        item['id'] = wp_post['guid']['rendered']
    elif post_id:
        item['id'] = post_id
    elif page_soup:
        post_url, post_id = find_post_url(page_soup, '')
        if post_id:
            item['id'] = post_id

    if wp_post:
        item['url'] = wp_post['link']
    elif meta_json and meta_json.get('og:url'):
        item['url'] = meta_json['og:url']
    elif ld_article and ld_article.get('url'):
        item['url'] = ld_article['url']
    elif ld_article and ld_article.get('mainEntityOfPage'):
        if isinstance(ld_article['mainEntityOfPage'], str):
            item['url'] = ld_article['mainEntityOfPage']
        elif isinstance(ld_article['mainEntityOfPage'], dict):
            item['url'] = ld_article['mainEntityOfPage']['@id']
    elif page_soup:
        el = page_soup.find('link', attrs={"rel": "canonical"})
        if el:
            item['url'] = el['href']
        else:
            item['url'] = url
    else:
        item['url'] = url
    if site_json.get('replace_netloc'):
        item['url'] = item['url'].replace(site_json['replace_netloc'][0], site_json['replace_netloc'][1])

    if site_json.get('title'):
        el = soup.find(site_json['title']['tag'], attrs=site_json['title']['attrs'])
        if el:
            item['title'] = el.get_text().strip()
    elif wp_post:
        item['title'] = BeautifulSoup('<p>{}</p>'.format(wp_post['title']['rendered']), 'html.parser').get_text()
    elif ld_article and ld_article.get('headline'):
        item['title'] = ld_article['headline']
    elif meta_json and meta_json.get('og:title'):
        if isinstance(meta_json['og:title'], list):
            item['title'] = meta_json['og:title'][0]
        else:
            item['title'] = meta_json['og:title']
    elif meta_json and meta_json.get('twitter:title'):
        if isinstance(meta_json['twitter:title'], list):
            item['title'] = meta_json['twitter:title'][0]
        else:
            item['title'] = meta_json['twitter:title']
    elif oembed_json and oembed_json['title']:
        item['title'] = oembed_json['title']
    elif ld_article and ld_article.get('name'):
        item['title'] = ld_article['name']
    elif page_soup:
        el = page_soup.find('title')
        if el:
            item['title'] = el.get_text()
    item['title'] = item['title'].replace('&amp;', '&')
    if re.search(r'&[#\w]+;', item['title']):
        item['title'] = html.unescape(item['title'])

    if wp_post:
        dt = datetime.fromisoformat(wp_post['date_gmt']).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(wp_post['modified_gmt']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    date = ''
    if wp_post:
        date = wp_post['date_gmt'] + '+00:00'
    elif meta_json and meta_json.get('article:published_time'):
        if isinstance(meta_json['article:published_time'], list):
            date = meta_json['article:published_time'][0]
        else:
            date = meta_json['article:published_time']
    elif ld_article and ld_article.get('datePublished'):
        date = ld_article['datePublished']
    elif page_soup:
        el = page_soup.find('time', attrs={"datetime": True})
        if el:
            date = el['datetime']
    if date:
        if date.endswith('Z'):
            date = date.replace('Z', '+00:00')
        if not re.search(r'[+\-]\d{2}:?\d{2}', date):
            dt_loc = datetime.fromisoformat(date)
            if site_json.get('timezone'):
                tz_loc = pytz.timezone(site_json['timezone'])
            else:
                tz_loc = pytz.timezone(config.local_tz)
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        else:
            dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    date = ''
    if wp_post:
        date = wp_post['modified_gmt'] + '+00:00'
    elif meta_json and meta_json.get('article:modified_time'):
        if isinstance(meta_json['article:modified_time'], list):
            date = meta_json['article:modified_time'][0]
        else:
            date = meta_json['article:modified_time']
    elif ld_article and ld_article.get('dateModified'):
        date = ld_article['dateModified']
    if date:
        if date.endswith('Z'):
            date = date.replace('Z', '+00:00')
        if not re.search(r'[+\-]\d{2}:?\d{2}', date):
            dt_loc = datetime.fromisoformat(date)
            if site_json.get('timezone'):
                tz_loc = pytz.timezone(site_json['timezone'])
            else:
                tz_loc = pytz.timezone(config.local_tz)
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        else:
            dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = get_authors(wp_post, yoast_json, page_soup, item, args, site_json, meta_json, ld_article, ld_people, oembed_json)
    if authors:
        for i in range(len(authors)):
            authors[i] = re.sub(r'^By ', '', authors[i], flags=re.I)
            authors[i] = re.sub(r'(.*?),\s?Associated Press$', r'\1 (Associated Press)', it, authors[i])
            authors[i] = authors[i].replace(',', '&#44;')
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)).replace('&#44;', ',')

    item['tags'] = []
    if site_json.get('tags'):
        for el in utils.get_soup_elements(site_json['tags'], soup):
            if el.name == 'a':
                item['tags'].append(el.get_text().strip())
            else:
                for it in el.find_all('a'):
                    item['tags'].append(it.get_text().strip())
    elif wp_post and wp_post.get('parsely') and wp_post['parsely'].get('meta') and wp_post['parsely']['meta'].get('keywords'):
        item['tags'] = wp_post['parsely']['meta']['keywords'].copy()
    elif wp_post and wp_post.get('parselyMeta') and wp_post['parselyMeta'].get('parsely-tags'):
        item['tags'] = wp_post['parselyMeta']['parsely-tags'].split(',')
    elif ld_article and ld_article.get('keywords'):
        if isinstance(ld_article['keywords'], list):
            item['tags'] = ld_article['keywords'].copy()
        elif isinstance(ld_article['keywords'], str):
            item['tags'] = list(map(str.strip, ld_article['keywords'].split(',')))
    elif meta_json and meta_json.get('article:tag'):
        if isinstance(meta_json['article:tag'], list):
            item['tags'] = meta_json['article:tag'].copy()
        elif isinstance(meta_json['article:tag'], str):
            item['tags'] = list(map(str.strip, meta_json['article:tag'].split(',')))
    elif meta_json and meta_json.get('parsely-tags'):
        item['tags'] = list(map(str.strip, meta_json['parsely-tags'].split(',')))
    elif meta_json and meta_json.get('keywords'):
        item['tags'] = list(map(str.strip, meta_json['keywords'].split(',')))
    elif wp_post and wp_post.get('_links') and wp_post['_links'].get('wp:term') and 'skip_wp_terms' not in args:
        for link in wp_post['_links']['wp:term']:
            if link.get('taxonomy') and link['taxonomy'] != 'author' and link['taxonomy'] != 'channel' and link['taxonomy'] != 'contributor' and link['taxonomy'] != 'site-layouts' and link['taxonomy'] != 'lineup':
                if site_json.get('replace_links_path'):
                    link_json = utils.get_url_json(link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1]))
                else:
                    link_json = utils.get_url_json(link['href'])
                if link_json:
                    for it in link_json:
                        if it.get('name'):
                            item['tags'].append(it['name'])
    elif wp_post.get('terms'):
        if wp_post['terms'].get('category'):
            for it in wp_post['terms']['category']:
                item['tags'].append(it['name'])
        if wp_post['terms'].get('post_tag'):
            for it in wp_post['terms']['post_tag']:
                item['tags'].append(it['name'])
    if item.get('tags'):
        # Remove duplicate tags - case insensitive
        # https://stackoverflow.com/questions/24983172/how-to-eliminate-duplicate-list-entries-in-python-while-preserving-case-sensitiv
        wordset = set(item['tags'])
        item['tags'] = [it for it in wordset if it.istitle() or it.title() not in wordset]
    else:
        del item['tags']


    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.startswith(site_json['wpjson_path']):
        n = 0
        feed = utils.init_jsonfeed(args)
        posts = utils.get_url_json(args['url'])
        if posts:
            for post in posts:
                if save_debug:
                    logger.debug('getting content from ' + post['link'])
                item = get_post_content(post, args, site_json, None, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed['items'].append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break
    else:
        feed = rss.get_feed(url, args, site_json, save_debug, get_content)
    return feed

