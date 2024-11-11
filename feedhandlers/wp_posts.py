import av, base64, bs4, html, json, math, pytz, random, re
import dateutil.parser
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import cnn, rss, wp

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, site_json, width=1200, height=800):
    # print(img_src)
    # if site_json and site_json.get('resize_image'):
    #     return utils.clean_url(img_src) +
    split_url = urlsplit(img_src)
    query = parse_qs(split_url.query)
    img_path = '{}://{}'.format(split_url.scheme, split_url.netloc)
    if site_json and site_json.get('img_path'):
        img_src = img_src.replace(img_path, site_json['img_path'])
        img_path = site_json['img_path']
    if site_json and site_json.get('use_webp'):
        # https://lazyadmin.nl/home-network/unifi-controller/
        img_src = re.sub(r'\.(jpe?g|png)(?!\.webp)', r'.\1.webp', img_src)
    if query.get('url'):
        # print(query)
        return img_src
    if query.get('w') or query.get('h') or query.get('fit'):
        return '{}{}?w={}'.format(img_path, split_url.path, width)
    if query.get('width') or query.get('height'):
        return '{}{}?width={}'.format(img_path, split_url.path, width)
    if query.get('resize') and not query.get('crop'):
        # print(query['resize'][0])
        m = re.search(r'(\d+),(\d+)', unquote_plus(query['resize'][0]))
        if m:
            w = int(m.group(1))
            h = int(m.group(2))
            height = math.floor(h * width / w)
            return '{}{}?resize={},{}'.format(img_path, split_url.path, width, height)
        return '{}{}?width={}'.format(img_path, split_url.path, width)
    if query.get('fit') and not query.get('crop'):
        # print(query['fit'][0])
        m = re.search(r'(\d+),(\d+)', unquote_plus(query['fit'][0]))
        if m:
            w = int(m.group(1))
            h = int(m.group(2))
            height = math.floor(h * width / w)
            return '{}{}?resize={},{}'.format(img_path, split_url.path, width, height)
    m = re.search(r'GettyImages-\d+(-\d+x\d+[^\.]*)', split_url.path)
    if m:
        return img_src.replace(m.group(1), '')
    m = re.search(r'/(\d+)xAny/', split_url.path)
    if m:
        return img_src.replace(m.group(0), '/{}xAny/'.format(width))
    m = re.search(r'-\d+x\d+(\.jpg|\.png)', split_url.path)
    if m:
        if utils.url_exists(img_src.replace(m.group(0), m.group(1))):
            return img_src.replace(m.group(0), m.group(1))
    return img_src


def add_image(el, el_parent, base_url, site_json, caption='', add_caption=True, decompose=True, insert=True, gallery=False, n=0, width=1000):
    # import inspect
    # curframe = inspect.currentframe()
    # calframe = inspect.getouterframes(curframe, 2)
    # logger.debug('add_image called from {}, line {}'.format(calframe[1][3], calframe[1][2]))

    # print(el)

    if el.name == None:
        return

    bg_img = False
    if el.name == 'img':
        img = el
    elif el.get('style') and 'background-image' in el['style']:
        img = el
        bg_img = True
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
    if it and it.get('href') and it['href'] != '#':
        if 'the5krunner.com' in it['href']:
            link = it['href'].replace('https://cdn.the5krunner.com/https://cdn.the5krunner.com', 'https://cdn.the5krunner.com')
        else:
            link = it['href']
    else:
        link = ''

    it = el.find(class_='nyp-slideshow-modal-image__icon')
    if it:
        it.decompose()

    if not el_parent:
        el_parent = el
        for it in reversed(el.find_parents()):
            # print('Parent: ' + it.name)
            if it.name == '[document]' or it.name in ['table', 'tbody', 'td', 'th', 'tr']:
                continue
            elif it.name in ['div', 'h1', 'h2', 'h3', 'p']:
                el_parent = it
                break

            #     has_str = False
            #     for c in it.contents:
            #         if isinstance(c, bs4.element.NavigableString) or (isinstance(c, bs4.element.Tag) and c.name in ['b', 'em', 'i', 'strong']):
            #             has_str = True
            #     if not has_str:
            #         el_parent = it
            #         break
            # elif not it.find('p'):
            #     el_parent = it
            #     break
        # if el.parent and el.parent.name == 'a' and el.parent.get('href'):
        #     el_parent = el.parent
        # if el_parent.parent and (el_parent.parent.name == 'center' or el_parent.parent.name == 'figure'):
        #     el_parent = el_parent.parent
        # if el_parent.parent and re.search(r'^(div|h\d|p)$', el_parent.parent.name):
        #     el_parent = el_parent.parent

    # print(el_parent['class'])
    # print(el_parent)

    # before = True
    # before_html = ''
    # after_html = ''
    # if el_parent.name in ['div', 'h1', 'h2', 'h3', 'p']:
    #     tags = []
    #     for c in it.contents:
    #         if isinstance(c, bs4.element.Tag):
    #             if c.name in ['figure', 'img']:
    #                 before = False
    #                 for tag in reversed(tags):
    #                     before_html += '</{}>'.format(tag)
    #                 tags = []
    #             else:
    #                 tags.append(c.name)
    #         elif isinstance(c, bs4.element.NavigableString):
    #             if c.strip():
    #                 if before:
    #                     if not before_html:
    #                         for tag in tags:
    #                             before_html += '<{}>'.format(tag)
    #                     before_html += c
    #                 else:
    #                     if not after_html:
    #                         after_html += start_tag
    #                     after_html += c
    #     if after_html:
    #         after_html += end_tag
    # print('Before: ' + before_html)
    # print('After: ' + after_html)
    # print('add_image el_parent = ' + str(el_parent))

    if link and 'www.youtube.com/watch' in link:
        new_html = utils.add_embed(link)
        if insert:
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

    img_src = ''
    if site_json and site_json.get('img_src') and img.get(site_json['img_src']):
        img_src = img[site_json['img_src']]
    if not img_src:
        if gallery:
            el_sources = el
        else:
            el_sources = el_parent
        if el_sources.find('source'):
            src = el_sources.find('source', attrs={"type": "image/webp"})
            if not src:
                src = el_sources.find('source', attrs={"type": "image/png"})
                if not src:
                    src = el_sources.find('source', attrs={"type": "image/jpg"})
            if src:
                if src.get('data-srcset'):
                    img_src = utils.image_from_srcset(src['data-srcset'], 1000)
                if src.get('srcset'):
                    img_src = utils.image_from_srcset(src['srcset'], 1000)
            if not img_src:
                images = []
                for src in el_sources.find_all('source'):
                    if src.get('srcset') and src.get('media'):
                        if 'min-width' in src['media']:
                            m = re.search(r'(\d+)px', src['media'])
                            if m:
                                image = {}
                                # image['src'] = src['srcset']
                                image['src'] = utils.image_from_srcset(src['srcset'], width)
                                image['width'] = utils.get_image_width(image['src'], True)
                                if image['width'] == -1:
                                    # This is not necessarily the real width
                                    image['width'] = int(m.group(1))
                                images.append(image)
                if images:
                    # print(images)
                    image = utils.closest_dict(images, 'width', 1000)
                    img_src = image['src']
    if not img_src:
        if bg_img:
            m = re.search(r'url\(([^\)]+)\)', img['style'])
            if m:
                img_src = m.group(1)
        elif link and img.get('class') and 'attachment-thumbnail' in img['class'] and ('.png' in link or '.jpg' in link):
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
        elif img.get('data-dt-lazy-src') and not img['data-dt-lazy-src'].startswith('data:image/gif;base64'):
            img_src = img['data-dt-lazy-src']
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
        elif img.get('nw18-data-src') and not img['nw18-data-src'].startswith('data:image/gif;base64'):
            img_src = img['nw18-data-src']
        else:
            img_src = img['src']

    # print(img_src, base_url)
    if img_src.startswith('//'):
        img_src = 'https:' + img_src
    elif img_src.startswith('/'):
        img_src = base_url + img_src

    if re.search(r'abyssalchronicles.*thumb_', img_src):
        img_src = img_src.replace('thumb_', 'normal_')
    elif re.search(r'www\.post-journal\.com.*?-\d+x\d+\.(jpe?g|png)', img_src):
        img_src = re.sub(r'^(.*?www\.post-journal\.com.*?)(-\d+x\d+)(\.jpe?g|png)', r'\1\3', img_src)

    # print(el.name)
    desc = ''
    captions = []
    if not bg_img:
        if el_parent.get('class') and 'multiple-images' in el_parent['class']:
            cap = '({})'.format(n)
            if add_caption:
                it = el_parent.find(class_='multiple-images__caption')
                if it:
                    captions.append(cap + '<br/><br/>' + it.decode_contents())
            else:
                captions.append(cap)
        if add_caption:
            if caption:
                captions.append(caption)
            elif el.get('class') and 'bp-embedded-image' in el['class']:
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
                else:
                    it = elm.find(class_=re.compile(r'image-attribution|image-credit|hds-credits|photo-credit|credits-overlay|credits-text|image_source|article-grid-img-credit|__credits|caption-owner|caption-credit|captionCredit'))
                    if it and it.get_text().strip():
                        credit = it.get_text().strip()
                    else:
                        it = elm.find(class_=['article-media__photographer', 'attribution', 'author-name', 'credit', 'credits', 'imageCredit', 'slide-credit', 'source', 'visual-by'])
                        if it and it.get_text().strip():
                            credit = it.get_text().strip()
                if it:
                    if it.get('class') and 'author-name' in it['class'] and it.find_parent(class_='author'):
                        it = it.find_parent(class_='author')
                    it.decompose()

                it = elm.find(class_='caption-content')
                if it and it.get_text().strip():
                    captions.append(it.decode_contents().strip())

                if not captions:
                    it = elm.find(class_='caption')
                    if it and it.get_text().strip():
                        if it.find(class_='description'):
                            it = it.find(class_='description')
                        captions.insert(0, it.decode_contents().strip())

                if not captions:
                    it = elm.find(class_=re.compile(r'wp-block-media-text__content|br-image.*-description|caption-content|caption-text|image-caption|img-caption|photo-layout__caption|article-media__featured-caption|m-article__hero-caption|media-caption|rslides_caption|slide-caption|atr-caption|article-grid-img-caption|__caption|inline_caption|r-inner|ie-custom-caption|phtcptn|captionText'))
                    if it and it.get_text().strip():
                        if it.find('p'):
                            captions.append(it.p.decode_contents().strip())
                        else:
                            captions.append(it.decode_contents().strip())

                if not captions:
                    it = elm.find(class_=re.compile(r'text'))
                    if it and it.name != 'figure' and it.get_text().strip():
                        captions.append(it.decode_contents().strip())

                if not captions:
                    it = elm.find(class_=['undark-caption', 'media-content'])
                    if it and it.get_text().strip():
                        captions.append(it.decode_contents().strip())

                if not captions:
                    it = elm.find(class_='box-text-inner')
                    if it and it.get_text().strip():
                        captions.append(it.decode_contents().strip())

                if not captions:
                    it = elm.find(class_='imgCaption')
                    if it and it.get_text().strip():
                        captions.append(re.sub(r'\W*$', '', it.decode_contents().strip()))

                if not captions:
                    it = elm.find(class_='singleImageCaption')
                    if it and it.get_text().strip():
                        i = it.find('i', class_='fas')
                        if i:
                            i.decompose()
                        captions.append(it.decode_contents().strip())

                if not captions:
                    for it in elm.find_all(class_=['elementor-image-box-title', 'elementor-image-box-description']):
                        captions.append(it.decode_contents().strip())

                if not captions:
                    it = elm.find('figcaption')
                    if it and it.get_text().strip():
                        captions.append(it.decode_contents().strip())

                if not captions:
                    it = elm.find('p', class_='image-note')
                    if it:
                        captions.append(it.decode_contents().strip())

                if not captions:
                    if img.get('data-image-caption'):
                        captions.append(img['data-image-caption'])
                    elif img.get('data-image-title') and not re.search(r'\w(_|-)\w||\w\d+$', img['data-image-title']):
                        captions.append(img['data-image-title'])

                if not captions:
                    it = el.find_next_sibling()
                    if it and it.get('class') and 'caption-hold' in it['class']:
                        captions.append(it.get_text())
                    else:
                        it = None

                if not captions and img.get('title'):
                    captions.append(img['title'])

                if it:
                    # print(it)
                    it.decompose()

                if credit:
                    captions.append(credit)

        if captions:
            for i in range(len(captions)):
                captions[i] = re.sub(r'</p>\s*<p>', '<br>', captions[i]).replace('<p>', '').replace('</p>', '')

        if el.find(class_='picture-desc'):
            it = el.find(class_='gallery-heading')
            if it and it.get_text().strip():
                desc += '<h3>{}</h3>'.format(it.get_text().strip())
            it = el.find(class_='gallery-content')
            if it and it.get_text().strip():
                it.attrs = {}
                it.name = 'p'
                desc += str(it)
            el.find(class_='picture-desc').decompose()
        elif el.find(class_='gallery-item__caption'):
            it = el.find(class_='gallery-item__caption')
            desc = it.decode_contents()
            it.decompose()

    if not (el.get('class') and 'bannerad' in el['class']):
        img_src = resize_image(img_src, site_json)
        if site_json and site_json.get('image_proxy'):
            img_src = 'https://wsrv.nl/?url=' + quote_plus(img_src)
        new_html = utils.add_image(img_src, ' | '.join(captions), link=link, desc=desc)
        if insert:
            new_el = BeautifulSoup(new_html, 'html.parser')
            try:
                el_parent.insert_before(new_el)
            except:
                el_parent.append(new_el)

    if decompose:
        if bg_img:
            img.decompose()
        elif len(el_parent.find_all('img')) > 1:
            el.decompose()
        else:
            def has_string(elm):
                for c in elm.contents:
                    if isinstance(c, bs4.element.NavigableString) and c.strip():
                        return True
                    elif isinstance(c, bs4.element.Tag):
                        if has_string(c):
                            return True
                return False
            if has_string(el_parent):
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
                    # print(block['tag'])
                    content_html += '<{0}>{1}</{0}>'.format(block['tag'],render_content(block['content'], url))
            else:
                logger.warning('unhandled dict block without tag')

        else:
            logger.warning('unhandled block type {}'.format(type(block)))

    return content_html


def get_page_soup(url, site_json, save_debug=False):
    page_html = utils.get_url_html(url, site_json=site_json)
    if not page_html:
        return None
    page_soup = BeautifulSoup(page_html, 'lxml')
    if save_debug:
        utils.write_file(page_html, './debug/page.html')
        # utils.write_file(str(page_soup), './debug/page.html')
    # format_content should handle this
    # if site_json:
    #     if site_json and site_json.get('decompose'):
    #         for it in site_json['decompose']:
    #             for el in utils.get_soup_elements(it, page_soup):
    #                 el.decompose()
    #     if site_json and site_json.get('unwrap'):
    #         for it in site_json['unwrap']:
    #             for el in utils.get_soup_elements(it, page_soup):
    #                 el.unwrap()
    #     if site_json and site_json.get('rename'):
    #         for it in site_json['rename']:
    #             for el in utils.get_soup_elements(it, page_soup):
    #                 el.name = it['name']
    return page_soup


def get_authors(wp_post, yoast_json, page_soup, item, args, site_json, meta_json=None, ld_article=None, ld_people=None, oembed_json=None):
    authors = []
    if site_json.get('author'):
        if not page_soup:
            page_soup = get_page_soup(item['url'], site_json)
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
                if authors and 'all_authors' not in site_json['author']:
                    break
    if authors:
        return authors

    if yoast_json and yoast_json.get('twitter_misc') and yoast_json['twitter_misc'].get('Written by'):
        authors.append(yoast_json['twitter_misc']['Written by'])
        return authors

    if wp_post:
        if wp_post.get('oht_article_byline'):
            for author in wp_post['oht_article_byline']:
                authors.append(re.sub(r'^By\s+', '', author, flags=re.I))
            return authors

        if wp_post.get('parsely') and wp_post['parsely'].get('meta') and wp_post['parsely']['meta'].get('author'):
            for author in wp_post['parsely']['meta']['author']:
                authors.append(author['name'])
            return authors

        if wp_post.get('parsely') and wp_post['parsely'].get('meta') and wp_post['parsely']['meta'].get('creator'):
            return wp_post['parsely']['meta']['creator'].copy()

        if wp_post.get('parselyMeta') and wp_post['parselyMeta'].get('parsely-author'):
            return wp_post['parselyMeta']['parsely-author'].copy()

        if wp_post.get('yoast_head_json') and wp_post['yoast_head_json'].get('twitter_misc') and wp_post['yoast_head_json']['twitter_misc'].get('Written by') and wp_post['yoast_head_json']['twitter_misc']['Written by'].lower() != 'administrator':
            authors.append(wp_post['yoast_head_json']['twitter_misc']['Written by'])
            return authors

        if wp_post.get('rj_fields') and wp_post['rj_fields'].get('_rj_field_byline_author') and wp_post['rj_fields']['_rj_field_byline_author'].get('authors'):
            return wp_post['rj_fields']['_rj_field_byline_author']['authors'].copy()

        if wp_post.get('meta') and wp_post['meta'].get('schneps_byline'):
            authors.append(re.sub(r'^By ', '', wp_post['meta']['schneps_byline'], flags=re.I))
            return authors

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

        if wp_post.get('author_data') and wp_post['author_data'].get('name'):
            authors.append(wp_post['author_data']['name'])
            return authors

        if wp_post.get('byline'):
            for it in wp_post['byline']:
                if isinstance(it, dict) and it.get('text'):
                    authors.append(it['text'])
            if authors:
                return authors

        if wp_post.get('bylines'):
            for it in wp_post['bylines']:
                if it.get('display_name'):
                    authors.append(it['display_name'])
            if authors:
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

        if not authors and wp_post.get('meta') and wp_post['meta'].get('extracredits'):
            authors.append(wp_post['meta']['extracredits'])
            return authors

        if not authors and wp_post.get('metadata') and wp_post['metadata'].get('author'):
            return wp_post['metadata']['author'].copy()

        if wp_post.get('yoast_head_json') and wp_post['yoast_head_json'].get('author'):
            authors.append(wp_post['yoast_head_json']['author'])
            return authors

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

        if 'skip_wp_term_author' not in args and wp_post.get('_links') and wp_post['_links'].get('wp:term'):
            for link in wp_post['_links']['wp:term']:
                if link.get('taxonomy') and link['taxonomy'] == 'author':
                    link_json = utils.get_url_json(link['href'])
                    if link_json:
                        for it in link_json:
                            authors.append(it['name'].replace('-', ' ').title())
        if authors:
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
        elif meta_json.get('cXenseParse:author'):
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
    if 'id' in post:
        item['id'] = post['id']
    elif 'guid' in post:
        if isinstance(post['guid'], str):
            item['id'] = post['guid']
        else:
            item['id'] = post['guid']['rendered']

    if site_json.get('replace_netloc'):
        item['url'] = post['link'].replace(site_json['replace_netloc'][0], site_json['replace_netloc'][1])
    else:
        item['url'] = post['link']

    if item['url'].startswith('/'):
        if post.get('_links') and post['_links'].get('about'):
            split_url = urlsplit(post['_links']['about'][0]['href'])
            item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, item['url'])

    split_url = urlsplit(item['url'])
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)
    paths = list(filter(None, split_url.path.split('/')))

    if post.get('yoast_head_json') and post['yoast_head_json'].get('og_title'):
        item['title'] = post['yoast_head_json']['og_title']
        if post['yoast_head_json'].get('og_site_name'):
            item['title'] = item['title'].replace(' | ' + post['yoast_head_json']['og_site_name'], '')
    elif post.get('title'):
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
        if 'multi_author' not in args:
            for i in range(len(authors)):
                # authors[i] = re.sub(r', (.*)', r' (\1)', authors[i])
                authors[i] = authors[i].replace(',', '&#44;')
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)).replace('&#44;', ',')
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
                if link.get('taxonomy') and link['taxonomy'] != 'author' and link['taxonomy'] != 'channel' and link['taxonomy'] != 'contributor' and link['taxonomy'] != 'site-layouts' and link['taxonomy'] != 'lineup' and link['taxonomy'] != 'content_type':
                    if site_json.get('replace_links_path'):
                        link_json = utils.get_url_json(link['href'].replace(site_json['replace_links_path'][0], site_json['replace_links_path'][1]))
                    else:
                        link_json = utils.get_url_json(link['href'])
                    if link_json:
                        for it in link_json:
                            if it.get('name'):
                                # print(it['name'])
                                item['tags'].append(it['name'])
    if yoast_json:
        keywords = next((it['keywords'] for it in yoast_json['@graph'] if isinstance(it, dict) and it.get('keywords')), None)
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
    if post.get('parselyMeta') and post['parselyMeta'].get('parsely-tags'):
        item['tags'] = post['parselyMeta']['parsely-tags'].split(',')
    if post.get('terms'):
        if post['terms'].get('category'):
            item['tags'] += [x['name'] for x in post['terms']['category']]
        if post['terms'].get('post_tag'):
            item['tags'] += [x['name'] for x in post['terms']['post_tag']]
    if post.get('class_list'):
        item['tags'] += [re.sub(r'^(category|topic)-', '', x) for x in post['class_list'] if not re.search(r'^(post|type|status|format|has)-', x)]
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
                        if link_json.get('media_details') and link_json['media_details'].get('image_meta'):
                            if link_json['media_details']['image_meta'].get('caption'):
                                captions.append(link_json['media_details']['image_meta']['caption'])
                            if link_json['media_details']['image_meta'].get('credit'):
                                captions.append(link_json['media_details']['image_meta']['credit'])
                        if not captions and link_json.get('description'):
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
                        if link_json.get('meta') and link_json['meta'].get('espn_photo_credit'):
                            captions.append(link_json['meta']['espn_photo_credit'])
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
                                if it.get('meta') and it['meta'].get('espn_photo_credit'):
                                    captions.append(it['meta']['espn_photo_credit'])
                                caption = ' | '.join(captions)
                                break
    if yoast_json:
        it = next((it for it in yoast_json['@graph'] if (isinstance(it, dict) and it.get('@type') and it['@type'] == '@ImageObject')), None)
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
        if item['_image'].startswith('//'):
            item['_image'] = 'https:' + item['_image']
        item['_image'] = resize_image(item['_image'], site_json)

    if post.get('yoast_head_json') and post['yoast_head_json'].get('og_description'):
        item['summary'] = post['yoast_head_json']['og_description']
    elif post.get('yoast_head_json') and post['yoast_head_json'].get('description'):
        item['summary'] = post['yoast_head_json']['description']
    elif post.get('meta') and post['meta'].get('summary'):
        item['summary'] = post['meta']['summary']
    elif post.get('meta') and post['meta'].get('long_summary'):
        item['summary'] = post['meta']['long_summary']
    elif post.get('excerpt') and isinstance(post['excerpt'], str):
        item['summary'] = post['excerpt']
    elif post.get('excerpt') and post['excerpt'].get('rendered') and isinstance(post['excerpt']['rendered'], str):
        item['summary'] = BeautifulSoup(post['excerpt']['rendered'], 'html.parser').get_text()
    elif yoast_json:
        it = next((it for it in yoast_json['@graph'] if it.get('description')), None)
        if it:
            item['summary'] = it['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
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
        elif 'convert_et_pb_entities' in args:
            content_html += re.sub(r'\[(/?et_pb_[^\]]+)\]', r'<\1>', post['content']['rendered'])
        else:
            content_html += post['content']['rendered']
        # utils.write_file(content_html, './debug/debug.html')
        if site_json.get('content'):
            content_soup = BeautifulSoup(content_html, 'html.parser')
            content_html = ''
            for el in utils.get_soup_elements(site_json['content'], content_soup):
                content_html += el.decode_contents()
    elif post.get('acf') and post['acf'].get('article_modules'):
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
    elif post.get('acf') and post['acf'].get('components'):
        # https://xpn.org/2024/05/08/remembering-steve-albini/
        if post['acf'].get('header_paragraph'):
            content_html += '<p><em>' + post['acf']['header_paragraph'] + '</em></p>'
        if post.get('better_featured_image'):
            content_html += utils.add_image(post['better_featured_image']['source_url'], post['better_featured_image'].get('caption'))
        for component in post['acf']['components']:
            if component['acf_fc_layout'] == 'bodytext':
                # content_html += component['body']
                content_html += format_content(component['body'], item, site_json)
            elif component['acf_fc_layout'] == 'video':
                if component['videoPlatform'] == 'YouTube':
                    content_html += utils.add_embed(component['videourl'])
                else:
                    logger.warning('unhandled acf video platform {} in {}'.format(component['videoPlatform'], item['url']))
            elif component['acf_fc_layout'] == 'embedcode':
                if component['code'].startswith('<iframe'):
                    m = re.search(r'src="([^"]+)"', component['code'])
                    content_html += utils.add_embed(m.group(1))
                elif 'xpn-rss.streamguys' in component['code']:
                    m = re.search(r'data-guid="([^"]+)"', component['code'])
                    embed_json = utils.get_url_json('https://utils.xpn.org/xpnRecast/v3/content.php?id=' + m.group(1))
                    if embed_json:
                        content_html += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}/videojs?src={1}"><img src="{0}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}/videojs?src={1}">{2} ({3})</a></span></div><div>&nbsp;</div>'.format(config.server, quote_plus(embed_json['url']), embed_json['title'], utils.calc_duration(embed_json['duration']))
                else:
                    logger.warning('unhandled acf embedcode in ' + item['url'])
            elif component['acf_fc_layout'] == 'carousel':
                for i, image in enumerate(component['images']):
                    if i > 0:
                        content_html += '<div>&nbsp;</div>'
                    content_html += utils.add_image(image['url'], image.get('caption'))
            elif component['acf_fc_layout'] == 'setlist':
                content_html += '<h2>Setlist</h2>'
                content_html += '<div style="font-size:1.2em; font-weight:bold;">' + component['artist_name'] + '</div>'
                content_html += '<div>' + component['album_name'] + '</div>'
                content_html += '<div>' + component['date'] + '</div>'
                content_html += '<ol>'
                for it in component['song_list']:
                    content_html += '<li>' + it['song_title'] + '</li>'
                content_html += '</ol>'
            elif component['acf_fc_layout'] == '':
                continue
            else:
                logger.warning('unhandled acf component type {} in {}'.format(component['acf_fc_layout'], item['url']))
        item['content_html'] = content_html
        return item
    elif post.get('type') and post['type'] == 'video':
        if post.get('excerpt') and post['excerpt'].get('rendered'):
            content_html += post['excerpt']['rendered']
        elif post.get('html_stripped_summary'):
            content_html += '<p>{}</p>'.format(post['html_stripped_summary'])
    elif post.get('type') and post['type'] == 'ndms_videos':
        # https://www.speedsport.com/video/sealed-under-pressure-spotlight-can-larson-catch-kinser/
        if not page_soup:
            if not page_soup:
                page_soup = get_page_soup(item['url'], site_json, save_debug)
            if page_soup:
                el = page_soup.find('script', string=re.compile(r'THEOplayer\.Player'))
                if el:
                    m = re.search(r'src:\s*"([^"]+)",\s*type:\s*"([^"]+)"', el.string)
                    if m:
                        video_src = m.group(1)
                        video_type = m.group(2)
                        m = re.search(r'poster:\s*"([^"]+)"', el.string)
                        if m:
                            poster = m.group(1)
                        else:
                            poster = ''
                        m = re.search(r'videoName_amp\s*=\s*"([^"]+)"', el.string)
                        if m:
                            caption = m.group(1)
                        else:
                            caption = ''
                        item['content_html'] = utils.add_video(video_src, video_type, poster, caption, use_videojs=True)
                        if 'embed' not in args and 'summary' in item:
                            item['content_html'] += '<p>' + item['summary'] + '</p>'
                        return item
    else:
        logger.warning('unknown post content in ' + item['url'])

    content_html = content_html.replace('\u2028', '')
    # print(content_html)

    lede = ''
    subtitle = ''
    if site_json.get('subtitle'):
        if not page_soup:
            page_soup = get_page_soup(item['url'], site_json, save_debug)
        if page_soup:
            subtitles = []
            for el in utils.get_soup_elements(site_json['subtitle'], page_soup):
                print(el)
                subtitles.append(el.get_text())
            if subtitles:
                if 'join' in site_json['subtitle']:
                    subtitle = site_json['subtitle']['join'].join(subtitles)
                else:
                    subtitle = '<br/>'.join(subtitles)
    else:
        if 'add_subtitle' in args and not isinstance(args['add_subtitle'], bool):
            if post.get(args['add_subtitle']):
                if isinstance(post[args['add_subtitle']], str):
                    subtitle = post[args['add_subtitle']]
                if isinstance(post[args['add_subtitle']], dict) and post[args['add_subtitle']].get('rendered'):
                    subtitle = re.sub(r'</?p>', '', post[args['add_subtitle']]['rendered'])
        elif post.get('subtitle'):
            subtitle = post['subtitle']
        elif post.get('sub_headline'):
            subtitle = post['sub_headline']['raw']
        elif post.get('rayos_subtitle'):
            subtitle = post['rayos_subtitle']
        elif post.get('dek'):
            subtitle = post['dek']
        elif post.get('acf') and post['acf'].get('post_subtitle'):
            subtitle = post['acf']['post_subtitle']
        elif post.get('acf') and post['acf'].get('dek'):
            subtitle = post['acf']['dek']
        elif post.get('acf') and post['acf'].get('deck'):
            subtitle = post['acf']['deck']
        elif post.get('meta'):
            if post['meta'].get('sub_title'):
                subtitle = post['meta']['sub_title']
            elif post['meta'].get('nbc_subtitle'):
                subtitle = post['meta']['nbc_subtitle']
            elif post['meta'].get('newspack_post_subtitle'):
                subtitle = post['meta']['newspack_post_subtitle']
            elif post['meta'].get('sub_heading'):
                subtitle = post['meta']['sub_heading']
            elif post['meta'].get('espn_subheading'):
                subtitle = post['meta']['espn_subheading']
            elif post['meta'].get('subheadline'):
                subtitle = post['meta']['subheadline']
            elif post['meta'].get('savage_platform_subheadline'):
                subtitle = post['meta']['savage_platform_subheadline']
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
        subtitle = re.sub(r'^<p>|</p>$', '', subtitle)
        lede += '<p><em>' + subtitle + '</em></p>'

    if post.get('type') and post['type'] == 'bc-video':
        args['skip_lede_img'] = True

    # print(lede)
    content_soup = BeautifulSoup(content_html, 'html.parser')
    for el in content_soup.contents:
        if el.name != None:
            if el.get('class') and 'wp-block-fuel-fuelshortcode' in el['class'] and el.find('fuel-video'):
                args['skip_lede_img'] = True
            break

    if 'skip_lede_img' not in args:
        video_lede = ''
        if post.get('lead_media') and re.search(r'wp:lakana/anvplayer', post['lead_media']['raw']):
            if post['lead_media'].get('feed'):
                video_feed = utils.get_url_json('https://feed.mp.lura.live/v2/feed/{}?start=0&fmt=json'.format(post['lead_media']['feed']))
                if video_feed:
                    params = parse_qs(urlsplit(video_feed['docs'][0]['media_url']).query)
                    if params.get('anvack'):
                        video_js = utils.get_url_html('https://tkx.mp.lura.live/rest/v2/mcp/video/{}?anvack={}'.format(video_feed['docs'][0]['obj_id'], params['anvack'][0]))
                        if video_js:
                            i = video_js.find('{')
                            j = video_js.rfind('}') + 1
                            video_json = json.loads(video_js[i:j])
                            # utils.write_file(video_json, './debug/video.json')
                            video_lede = utils.add_video(video_json['published_urls'][0]['embed_url'], 'application/x-mpegURL', video_json['src_image_url'], video_json['def_title'])
            else:
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
                    if article_json.get('associatedMedia'):
                        for it in article_json['associatedMedia']:
                            if it['@type'] == 'VideoObject' and it.get('contentUrl'):
                                video_lede = utils.add_video(it['contentUrl'], 'application/x-mpegURL', it['thumbnailUrl'], it['name'])
                                break
                if not video_lede:
                    if not page_soup:
                        page_soup = get_page_soup(item['url'], site_json, save_debug)
                    if page_soup:
                        el = page_soup.find(class_='article-featured-media--lakanaanvplayer')
                        if el:
                            # print(el)
                            it = el.find(attrs={"data-video_params": True})
                            if it:
                                # https://www.wate.com/news/dr-dre-says-he-had-3-strokes-after-2021-brain-aneurysm/
                                video_json = json.loads(html.unescape(it['data-video_params']).replace("'/", '"'))
                                # utils.write_file(video_json, './debug/video.json')
                                lura_json = {
                                    "anvack": video_json['accessKey'],
                                    "accessKey": video_json['accessKey'],
                                    "token": video_json['token'],
                                    "v": video_json['video']
                                }
                                lura_url = 'https://w3.mp.lura.live/player/prod/v3/anvload.html?key=' + quote(base64.b64encode(json.dumps(lura_json).replace(' ', '').encode('utf-8')).decode('utf-8'))
                                video_lede = utils.add_embed(lura_url)
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
                        page_soup = get_page_soup(item['url'], site_json, save_debug)
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
                    page_soup = get_page_soup(item['url'], site_json, save_debug)
                if page_soup:
                    el = page_soup.find(attrs={"data-react-component": "VideoPlayer"})
                    if el:
                        video_meta = json.loads(html.unescape(el['data-meta']))
                    else:
                        el = page_soup.find(attrs={"data-react-component": "VideoPlaylist"})
                        if el:
                            video_props = json.loads(html.unescape(el['data-props']))
                            video_meta = video_props['videos'][0]
                    el = page_soup.find('script', string=re.compile(r'var nbc ='))
                    if el:
                        i = el.string.find('{')
                        j = el.string.rfind('}') + 1
                        nbc_json = json.loads(el.string[i:j])
            else:
                video_meta = post['meta']
            if video_meta:
                if video_meta.get('mp4Url'):
                    video_lede += utils.add_video(video_meta['mp4Url'], 'video/mp4', video_meta.get('poster'), video_meta.get('title'))
                else:
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
                page_soup = get_page_soup(item['url'], site_json, save_debug)
            if page_soup:
                el = page_soup.find('video', attrs={"data-video-id-pending": post['meta']['featured_bc_video_id']['id']})
                if el:
                    video_lede = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(el['data-account'], el['data-player'], el['data-video-id-pending']))
        elif post.get('you_tube_id'):
            video_lede = utils.add_embed('https://www.youtube.com/watch?v=' + post['you_tube_id'])
        elif site_json.get('lede_video'):
            if not page_soup:
                page_soup = get_page_soup(item['url'], site_json, save_debug)
            if page_soup:
                el = utils.get_soup_elements(site_json['lede_video'], page_soup)
                print(el)
                if el:
                    it = el[0].find(class_='c-videoPlay')
                    if it and it.get('data-displayinline'):
                        video_lede = utils.add_embed(it['data-displayinline'])
                    elif el[0].find(class_='rsm-citynews-video-player'):
                        it = el[0].find('video-js')
                        video_url = 'https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(it['data-account'], it['data-player'], it['data-video-id'])
                        video_lede = utils.add_embed(video_url)
                    elif 'video-js' in el[0]['class']:
                        video_url = 'https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(el[0]['data-account'], el[0]['data-player'], el[0]['data-video-id'])
                        video_lede = utils.add_embed(video_url)
        if video_lede:
            lede += video_lede
        elif post.get('content') and re.search(r'^\s*<p><script[^>]+src="https://newsource-embed-prd\.ns\.cnn\.com/videos/embed', post['content']['rendered']):
            # https://krdo.com/politics/cnn-us-politics/2024/03/07/takeaways-from-joe-bidens-state-of-the-union-address-2/
            pass
        elif site_json.get('lede_img'):
            if not page_soup:
                page_soup = get_page_soup(item['url'], site_json, save_debug)
            if page_soup:
                elements = utils.get_soup_elements(site_json['lede_img'], page_soup)
                if elements:
                    lede += add_image(elements[0], elements[0], base_url, site_json)
        elif item.get('_image'):
            img_path = urlsplit(item['_image']).path
            if '.mp4.' in item['_image']:
                video_src = item['_image'].split('.mp4')[0] + '.mp4'
                lede += utils.add_video(video_src, 'video/mp4', item['_image'])
            elif '/www.post-journal.com/images' in img_path:
                if not re.search(re.sub(r'\.(jpe?g|png)', '', img_path), content_html, flags=re.I):
                    lede += utils.add_image(resize_image(item['_image'], site_json), caption)
            elif not re.search(img_path, content_html, flags=re.I) or 'add_lede_img' in args:
                # Add lede image if it's not in the content or if add_lede_img arg
                if 'image_proxy' in site_json and site_json['image_proxy']:
                    lede += utils.add_image('https://wsrv.nl/?url=' + quote_plus(item['_image']), caption)
                else:
                    lede += utils.add_image(resize_image(item['_image'], site_json), caption)

    # print(lede)
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

    if re.search(r'makezine\.com/(projects|products)', item['url']):
        if not page_soup:
            page_soup = get_page_soup(item['url'], site_json, save_debug)
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
            page_soup = get_page_soup(item['url'], site_json, save_debug)
        for it in site_json['add_content']:
            sep_lede = False
            sep_foot = False
            elements = utils.get_soup_elements(it, page_soup)
            if elements:
                for el in elements:
                    if it.get('position') and it['position'] == 'top':
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


def format_content(content_html, item, site_json=None, module_format_content=None, page_soup=None):
    utils.write_file(content_html, './debug/debug.html')

    split_url = urlsplit(item['url'])
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)

    soup = BeautifulSoup(content_html, 'html.parser')

    # remove comments
    for el in soup.find_all(text=lambda text: isinstance(text, Comment)):
        el.extract()

    if site_json:
        if site_json.get('rename'):
            for it in site_json['rename']:
                for el in utils.get_soup_elements(it, soup):
                    el.name = it['name']

        if site_json.get('replace'):
            for it in site_json['replace']:
                for el in utils.get_soup_elements(it, soup):
                    el.replace_with(BeautifulSoup(it['new_html'], 'html.parser'))

        if site_json.get('decompose'):
            for it in site_json['decompose']:
                for el in utils.get_soup_elements(it, soup):
                    el.decompose()

        if site_json.get('unwrap'):
            for it in site_json['unwrap']:
                for el in utils.get_soup_elements(it, soup):
                    el.unwrap()

    el = soup.find('body')
    if el:
        soup = el

    el = soup.find(class_='entry-content')
    if el:
        soup = el

    for el in soup.find_all('pba-embed'):
        new_html = html.unescape(el['code'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    utils.write_file(str(soup), './debug/debug2.html')

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
        if el.name == None:
            continue
        if el.get('id') and el['id'].startswith('slideshow_slide_'):
            continue
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
            el.replace_with(new_el)
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

    for el in soup.find_all('span', class_=['keystone-icon', 'key-feature-icon']):
        # https://emojipedia.org/
        el['style'] = 'font-size:2em;'
        if 'tr__battery_colour' in el['class']:
            el.string = '🔋'
        elif 'tr__clock_colour' in el['class'] or 'tr__24hours_colour' in el['class']:
            el.string = '⏲️'
        elif 'tr__headphones_colour' in el['class'] or 'tr__earphones_colour' in el['class'] or 'tr__wirelessearphones_colour' in el['class']:
            el.string = '🎧'
        elif 'tr__speaker_colour' in el['class'] or 'tr__sound_colour' in el['class'] or 'tr__volume_colour' in el['class']:
            el.string = '🔊'
        elif 'tr__camera_colour' in el['class'] or 'tr__DSLR_colour' in el['class']:
            el.string = '📷'
        elif 'tr__camerashutter_colour' in el['class']:
            el.string = '📷'
        elif 'tr__smarthome_colour' in el['class']:
            el.string = '🏠'
        elif 'tr__music_colour' in el['class'] or 'tr__musicstreaming_colour' in el['class']:
            el.string = '🎵'
        elif 'tr__creditcard_colour' in el['class']:
            el.string = '💳'
        elif 'tr__dna_colour' in el['class']:
            el.string = '🧬'
        elif 'tr__donotdisturb_colour' in el['class']:
            el.string = '🚫'
        elif 'tr__usb_colour' in el['class']:
            el.string = '🔌'
        elif 'tr__world_colour' in el['class']:
            el.string = '🌎'
        elif 'tr__car_colour' in el['class']:
            el.string = '🚗'
        elif 'tr__pc_colour' in el['class'] or 'tr__laptopwireless_colour' in el['class'] or 'tr__processor_colour' in el['class'] or 'tr__RAM_colour' in el['class']:
            el.string = '💻'
        elif 'tr__wristwatch_colour' in el['class']:
            el.string = '⌚'
        elif 'tr__screen_colour' in el['class']:
            el.string = '🖥'
        elif 'tr__heart_colour' in el['class']:
            el.string = '❤️'
        elif 'tr__microphone_colour' in el['class']:
            el.string = '🎙️'
        elif 'tr__mixer_colour' in el['class']:
            el.string = '🎛️'
        elif 'tr__temperature_colour' in el['class']:
            el.string = '🌡'
        elif 'tr__wind_colour' in el['class']:
            el.string = '💨'
        elif 'tr__lightbulb_colour' in el['class']:
            el.string = '💡'
        elif 'tr__videoclip_colour' in el['class']:
            el.string = '🎞️'
        elif 'tr__kettle_colour' in el['class']:
            el.string = '🫖️'
        elif 'tr__alien_colour' in el['class']:
            el.string = '🫖️'
        elif 'tr__coffee_colour' in el['class']:
            el.string = '☕️'
        elif 'tr__paintbrushes_colour' in el['class']:
            el.string = '🖌️'
        elif 'tr__console_colour' in el['class'] or 'tr__gamepad_colour' in el['class']:
            el.string = '🎮️'
        elif 'tr__key_colour' in el['class']:
            el.string = '🔑'
        elif 'tr__dimensions_colour' in el['class'] or 'tr__phonedimensions_colour' in el['class']:
            el.string = '📏'
        elif 'tr__coins_colour' in el['class']:
            el.string = '🪙'
        elif 'tr__tv_colour' in el['class'] or 'tr__connectedtv_colour' in el['class'] or 'tr__tvunit_colour' in el['class']:
            el.string = '📺'
        elif 'tr__oscar_colour' in el['class']:
            el.string = '🏆'
        elif 'tr__eye_colour' in el['class']:
            el.string = '👁️'
        elif 'tr__vr_colour' in el['class']:
            el.string = '🥽'
        elif 'tr__search_colour' in el['class']:
            el.string = '🔍'
        elif 'tr__basket_colour' in el['class']:
            el.string = '🧺'
        elif 'tr__waterdroplets_colour' in el['class']:
            el.string = '💦'
        elif 'tr__rain_colour' in el['class']:
            el.string = '🌧️'
        elif 'tr__apple_colour' in el['class']:
            el.string = '🍎'
        elif 'tr__signal_colour' in el['class']:
            el.string = '📶'
        elif 'tr__balanced_colour' in el['class'] or 'tr__weight_colour' in el['class']:
            el.string = '⚖️'
        elif 'tr__wallet_colour' in el['class']:
            el.string = '💵'
        elif 'tr__tablet_colour' in el['class']:
            el.string = '📱'
        elif 'tr__champagne_colour' in el['class']:
            el.string = '🥂'
        elif 'tr__energybolt_colour' in el['class']:
            el.string = '⚡'
        elif 'tr__pencil_colour' in el['class']:
            el.string = '⚡'
        elif 'tr__bed_colour' in el['class']:
            el.string = '⚡'
        elif 'tr__heartbeat_colour' in el['class']:
            el.string = '💓'
        elif 'tr__backpack_colour' in el['class']:
            el.string = '🎒'
        elif 'tr__colour_colour' in el['class']:
            el.string = '🎨'
        elif 'tr__robot_colour' in el['class']:
            el.string = '🤖'
        elif 'tr__key_colour' in el['class'] or 'tr__shift_colour' in el['class']:
            el.string = '⌨️'
        elif 'tr__filesystem_colour' in el['class']:
            el.string = '📂'
        elif 'tr__journey_colour' in el['class']:
            el.string = '🗺️'
        elif 'tr__like_colour' in el['class']:
            el.string = '👍'
        elif 'tr__24hoursupport_colour' in el['class']:
            el.string = '📞'
        else:
            el.string = '✅'
            logger.warning('unhandled keystone-icon {} in {}'.format(el['class'], item['url']))

    for el in soup.find_all(re.compile(r'^h\d')):
        it = el.find(attrs={"style": True})
        if it:
            it.unwrap()

    for el in soup.find_all(['h5', 'h6']):
        # too small
        el.name = 'h4'

    for el in soup.find_all('h2', class_='entry-title'):
        if el.a:
            new_html = utils.add_embed(el.a['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)

    for el in soup.find_all('span', class_='neFMT_Subhead_WithinText'):
        el['style'] = 'font-size:1.2em; font-weight:bold;'

    for el in soup.find_all('p', class_='tpd-subheader'):
        el.attrs = {}
        el['style'] = 'font-style:italic;'

    for el in soup.find_all('p', class_='title'):
        it = el.find_next_sibling('p')
        links = it.find_all('a')
        if links:
            new_html = '<p><em>' + el.get_text().strip() + ': </em>'
            new_html += ', '.join([str(x) for x in links])
            new_html += '</p>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
            it.decompose()

    for el in soup.find_all('div', class_='calmatters-summary'):
        it = el.find(class_='wp-block-group__inner-container')
        if it:
            new_html = utils.add_blockquote(it.decode_contents())
        else:
            new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('div', class_='mntl-sc-block-callout'):
        new_html = '<fieldset style="border:1px black solid; border-radius:10px;"><legend style="font-size:1.1em; font-weight:bold; margin-left:8px; padding:4px 8px;">'
        if 'theme-news-summary' in el['class']:
            new_html += 'Why This Matters'
        elif 'theme-keyfeatures' in el['class']:
            new_html += 'Key Takeaways'
        elif 'theme-experttipnote' in el['class']:
            new_html += 'Note'
        elif 'theme-generic' in el['class']:
            it = el.find(class_='mntl-sc-block-callout-heading')
            if it:
                new_html += it.get_text().strip()
            else:
                logger.warning('unknown mntl-sc-block-callout heading in ' + item['url'])
        else:
            new_html += 'Summary'
            logger.warning('unknown mntl-sc-block-callout title in ' + item['url'])
        new_html += '</legend>'
        it = el.find(class_='mntl-sc-block-callout-body')
        if it:
            new_html += it.decode_contents()
        new_html += '</fieldset><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('div', class_='mntl-sc-block-faq'):
        new_html = '<fieldset style="border:1px #B22222 solid; border-radius:10px;"><legend style="font-size:1.2em; font-weight:bold; margin-left:8px; padding:4px 8px;">FAQ</legend>'
        for it in el.find_all('li', class_='accordion__item'):
            new_html += '<div style="font-size:1.05em; font-weight:bold;">' + it.find(class_='accordion__title').get_text().strip() + '</div>'
            new_html += it.find(class_='faq-accordion__item-answer').decode_contents()
        new_html += '</fieldset><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    # for el in soup.find_all('table', attrs={"width": True}):
    #     el.attrs = {}
    #     el['style'] = 'width:100%;'

    for el in soup.find_all('table'):
        if el.find('a', {"href": re.compile(r'youtube.com/@')}):
            continue
        el['style'] = 'width:100%; border-collapse:collapse;'
        for i, it in enumerate(el.find_all('tr')):
            if i % 2 == 0:
                it['style'] = 'background-color:#aaa;'
            else:
                it['style'] = ''
        for it in el.find_all(['td', 'th']):
            it['style'] = 'padding:12px 8px; border:1px solid black;'
        it = el.find_parent('figure')
        if it:
            it['style'] = 'margin:0; padding:0;'
            if it.figcaption:
                it.figcaption['style'] = 'font-size:0.83em;'

    for el in soup.find_all(class_='has-text-align-center'):
        el['style'] = 'text-align:center;'

    for el in soup.find_all(class_='summary__title'):
        new_html = '<h2>{}</h2>'.format(el.get_text())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-buttons'):
        it = el.find(class_='wp-block-button__link')
        if it:
            new_html = utils.add_button(it['href'], it.get_text())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled wp-block-buttons in ' + item['url'])

    for el in soup.select('p.comp-p:has(> a.comp-button)'):
        new_html = utils.add_button(el.a['href'], el.a.get_text())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='button_cont'):
        #https://www.anadventurousworld.com/osprey-sojourn-porter-30l-review/
        new_html = utils.add_button(utils.get_redirect_url(el.a['href']), el.a.get_text())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_=['wp-block-prc-block-subtitle', 'br-excerpt']):
        new_html = '<p><em>{}</em></p>'.format(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        soup.insert(0, new_el)
        el.decompose()

    for el in soup.find_all('p', class_=['has-drop-cap', 'dropcap', 'drop-cap', 'add-drop-cap']):
        new_html = re.sub(r'^(<[^>]+>)(<[^>]+>)?(\W*\w)', r'\1\2<span style="float:left; font-size:4em; line-height:0.8em;">\3</span>', str(el), 1)
        new_html += '<span style="clear:left;"></span>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('span', class_=['big-cap', 'dropcap', 'drop-cap', 'firstcharacter', 'big-letter']):
        el.attrs = {}
        el['style'] = 'float:left; font-size:4em; line-height:0.8em;'
        new_el = BeautifulSoup('<span style="clear:left;"></span>', 'html.parser')
        el.find_parent('p').insert_after(new_el)

    for el in soup.find_all('div', class_='show-dropcap'):
        # https://www.quantamagazine.org/john-wheeler-saw-the-tear-in-reality-20240925/
        it = el.find('span')
        if it and len(it.get_text().strip()) == 1:
            it['style'] = 'float:left; font-size:4em; line-height:0.8em;'
            new_el = BeautifulSoup('<span style="clear:left;"></span>', 'html.parser')
            it.find_parent('p').insert_after(new_el)
            el.unwrap()
        else:
            it = el.find('p')
            if it:
                new_html = '<p>' + re.sub(r'(^\w)(.*)', r'<span style="float:left; font-size:4em; line-height:0.8em;">\1</span>\2', it.decode_contents()) + '</p><span style="clear:left;"></span>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                it.replace_with(new_el)
                el.unwrap()
            else:
                logger.warning('unhandled show-dropcap in ' + item['url'])

    for el in soup.find_all('div', class_='intro-text'):
        el['style'] = 'font-size:1.1em; font-style:italic;'

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

    for el in soup.select('h2:has(> span.ez-toc-section)'):
        if 'pokemongohub.net' in item['url']:
            # https://pokemongohub.net/post/article/8th-anniversary-event-pvp-review/
            new_html = '<div style="display:flex; align-items:center; padding:18px; border-radius:12px; background:linear-gradient(45deg, var(--tint) 80%, #00000033 80%); --tint:#00a965;">'
            new_html += '<div style="color:white; font-size:1.5em; font-weight:bold;">' + el.get_text().strip() + '</div>'
            it = el.find(class_='flat-icon')
            if it:
                new_html += '<div style="margin-left: auto;"><img src="{}" style="height:52px; width:52px;"/></div>'.format(it.img['src'])
            new_html += '</div>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            el.span.unwrap()

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
        el.replace_with(new_el)

    for el in soup.find_all(id='story-highlights'):
        # https://coinpedia.org/news/crypto-bloodbath-why-is-crypto-crashing-right-now/
        new_html = ''
        it = el.find(class_='the-subtitle')
        if it:
            new_html += '<h3>' + it.get_text().strip() + '</h3>'
        if el.find('ul'):
            new_html += '<ul>'
            for it in el.select('li p.highlight'):
                new_html += '<li>' + it.get_text().strip() + '</li>'
            new_html += '</ul><hr/>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled story-highlights in ' + item['url'])

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
            new_html += '<div style="flex:1; min-width:256px;">{}</div>'.format(add_image(it, None, base_url, site_json).replace('width:100%;', 'width:100%;').replace('max-height:800px;', 'max-height:300px;'))
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
                # if img.img.get('srcset'):
                #     img_src = utils.image_from_srcset(img.img['srcset'], 160)
                # else:
                #     img_src = img.img['src']
                # new_html += '<div style="flex:1; min-width:128px; max-width:160px; margin:auto;"><img style="width:100%;" src="{}"/></div>'.format(img_src)
                new_html += '<div style="flex:1; min-width:256px; margin:auto;">' + add_image(img, img, base_url, site_json) + '</div>'
            else:
                new_html += '<div style="flex:2; min-width:256px;">{}</div>'.format(it.decode_contents())
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(id='post-capsule-block'):
        it = el.find(class_='capsule-crashline')
        if it:
            it.attrs = {}
            it.name = 'h2'
        it = el.find(class_='image-hero')
        if it:
            new_el = BeautifulSoup(utils.add_image(it['src']))
            it.replace_with(new_el)
        it = el.find(class_='capsule-headline')
        if it:
            it.attrs = {}
            it.name = 'div'
            it['style'] = 'font-size:1.2em; font-weight:bold; border-top:1px solid black;'
        it = el.find(class_='capsule-subhead')
        if it:
            it.attrs = {}
            it.name = 'div'
            it['style'] = 'font-size:0.9em; font-weight:bold; color:#555; text-transform:uppercase;'
        it = el.find(class_='capsule-body')
        if it:
            it.unwrap()
        el.unwrap()

    for el in soup.select('div:has(> amp-live-list)'):
        # https://www.independent.co.uk/sport/olympics/olympics-2024-live-paris-results-b2587399.html
        new_html = ''
        for post in el.find_all('div', id=re.compile(r'post-')):
            dt = datetime.fromisoformat(post.find('amp-timeago')['datetime'])
            new_html += '<div style="font-weight:bold;">&bull;&nbsp;' + utils.format_display_date(dt) + '</div>'
            new_html += '<div style="border-left:3px solid #ccc; margin-left:0.3em; padding:0.5em 1em;">'
            post_body = post.find('div')
            if post_body:
                for it in post_body.select('div:has(> div.image):has(> h3):has(> p)'):
                    new_el = BeautifulSoup(utils.add_embed(it.find('a')['href']), 'html.parser')
                    it.replace_with(new_el)
                for it in post_body.select('div.image:has(> figure)'):
                    # new_el = BeautifulSoup(add_image(it, it, base_url, site_json, decompose=False), 'html.parser')
                    new_el = BeautifulSoup(utils.add_image(it.figure.img['src']), 'html.parser')
                    it.replace_with(new_el)
                for it in post_body.select('div.twitter-post'):
                    new_el = BeautifulSoup(utils.add_embed('https://twitter.com/__/status/' + it.find('amp-twitter')['data-tweetid']), 'html.parser')
                    it.replace_with(new_el)
                for it in post_body.select('div:has(> figure div#video_holder iframe)'):
                    new_el = BeautifulSoup(utils.add_embed(it.find('iframe')['src']), 'html.parser')
                    it.replace_with(new_el)
                for it in post_body.find_all('div', class_=True, recursive=False):
                    it.unwrap()
                new_html += post_body.decode_contents()
            it = post_body.find_next_sibling('div')
            if it:
                it = it.find_all('span')
                if len(it) == 2:
                    new_html += '<p><em>Posted by: ' + it[0].get_text().strip() + '</em></p>'
            new_html += '<div>&nbsp;</div></div>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled amp-live-list in ' + item['url'])

    for el in soup.find_all(class_='blog-updt-row'):
        # https://www.firstpost.com/sports/paralympics-2024-live-score-today-india-archery-taekwondo-badminton-online-free-streaming-29-august-13809342.html
        new_html = '<div><span style="color:#ccc;">⬤</span>&nbsp;'
        it = el.find(class_='bg-dt')
        if it:
            date = it.get_text().strip()
            tz_loc = None
            m = re.search(r'\(([A-Z]+)\)', date)
            if m:
                if m.group(1) == 'IST':
                    tz_loc = pytz.timezone('Asia/Calcutta')
            if not tz_loc:
                logger.warning('unknown bg-dt timezone {} in {}'.format(m.group(1), item['url']))
                tz_loc = pytz.timezone(config.local_tz)
            try:
                dt_loc = dateutil.parser.parse(re.sub(r'\s*\([A-Z]+\)', '', date))
                dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                date = utils.format_display_date(dt)
            except:
                pass
            new_html += '<span style="font-size:0.8em;">' + date + '</span>'
        new_html += '</div><div style="margin-left:0.35em; padding-left:8px; border-left:;border-left:3px solid #ccc;">'
        it = el.find(class_='blg-ttl')
        if it:
            new_html += '<div style="font-size:1.05em; font-weight:bold;">' + it.get_text().strip() + '</div>'
        it = el.find(class_='blog-txt')
        if it:
            for elm in it.select('p:has(> img)'):
                elm.unwrap()
            for elm in it.find_all('img'):
                add_image(elm, elm, base_url, site_json)
            if it.p:
                text = it.decode_contents()
            else:
                it.attrs = {}
                text = str(it)
            try:
                new_html += text.encode('iso-8859-1').decode('utf-8')
            except:
                new_html += text
        new_html += '<div>&nbsp;</div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='js-react-hydrator'):
        new_html = ''
        if el.get('data-component-props'):
            # data_props = html.unescape(el['data-component-props']).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            # print(data_props[34404:34410])
            # data_json = json.loads(data_props)
            utils.write_file(el['data-component-props'], './debug/data.txt')
        if not new_html:
            logger.warning('unhandled js-react-hydrator in ' + item['url'])

    for el in soup.find_all(class_='poll'):
        # https://www.nintendolife.com/news/2024/09/poll-what-is-your-favourite-game-in-the-marvel-vs-capcom-fighting-collection
        new_html = ''
        if el.find(class_='poll-results'):
            it = el.find('h3')
            if it:
                it.attrs = {}
                new_html += str(it)
            for li in el.find_all('li', class_='result'):
                val = 0.0
                it = li.find(attrs={"title": True})
                if it:
                    m = re.search(r'([\d\.]+)%', it['title'])
                    if m:
                        val = float(m.group(1))
                new_html += utils.add_bar(li.find(class_='answer').get_text().strip(), val, 100)
            new_html += '<div>&nbsp;</div>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled poll in ' + item['url'])

    for el in soup.find_all(class_='positive-negative'):
        # https://www.nintendolife.com/reviews/switch-eshop/jackbox-naughty-pack
        new_html = ''
        it = el.find('ul', class_='positives')
        if it:
            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            it.attrs = {}
            new_html += '<div style="flex:1; min-width:360px;"><div style="font-size:1.1em; font-weight:bold;">Positives</div>' + str(it) + '</div>'
            it = el.find('ul', class_='negatives')
            if it:
                it.attrs = {}
                new_html += '<div style="flex:1; min-width:360px;"><div style="font-size:1.1em; font-weight:bold;">Positives</div>' + str(it) + '</div>'
            new_html += '</div>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled positive-negative in ' + item['url'])

    for el in soup.find_all(class_='scoring'):
        # https://www.nintendolife.com/reviews/switch-eshop/jackbox-naughty-pack
        new_html = ''
        it = el.select('p.score > span.value')
        if it:
            score = it[0].get_text().strip()
            it = el.select('p.score > span.best')
            if it:
                max_score = it[0].get_text().strip()
            else:
                max_score = '10'
            new_html += utils.add_stars(int(score), int(max_score))
            new_html += '<div style="font-size:2em; font-weight:bold; text-align:center;">'
            it = el.select('p.score > span.accent')
            if it:
                new_html += it[0].get_text().strip() + ' &ndash; '
            new_html += score + '<span style="font-size:0.5em;">/' + max_score + '</span></div><div>&nbsp;</div>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled scoring in ' + item['url'])

    for el in soup.find_all(class_='single-score'):
        # https://thespool.net/reviews/movies/film-review-beverly-hills-cop-axel-f-netflix-2024-eddie-murphy/
        new_html = '<div style="text-align:center; font-size:3em; font-weight:bold;">' + el.get_text().strip() + '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)


    for el in soup.find_all(class_='summary-panel'):
        # https://thespool.net/reviews/movies/film-review-beverly-hills-cop-axel-f-netflix-2024-eddie-murphy/
        new_html = '<ul>'
        for it in el.find_all(class_='summary-panel-single'):
            links = [str(link) for link in it.find_all('a')]
            if links:
                new_html += '<li>' + it.span.get_text().strip() + ': ' + ', '.join(links) + '</li>'
        new_html += '</ul>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='reviewRatings'):
        # https://lwlies.com/reviews/longlegs/
        for it in el.find_all(class_='reviewScore'):
            new_html = '<table><tr><td style="font-size:3em; font-weight:bold;">'
            rating = it.find(class_=re.compile(r'icon-rating'))
            if rating:
                m = re.search(r'icon-rating(\d+)', ' '.join(rating['class']))
                new_html += html.unescape('&#{};'.format(9311 + int(m.group(1))))
                rating.decompose()
            new_html += '</td><td style="padding-left:8px;">' + it.decode_contents() + '</td></tr></table>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            it.replace_with(new_el)
        el.unwrap()

    for el in soup.find_all(class_='review-box'):
        # https://gizmodo.com/iphone-16-pro-review-2000499940
        new_html = '<div style="border:1px solid black; border-radius:10px; padding:8px; margin:0 1em 0 1em;">'
        for it in el.select('div.border > p', recursive=False):
            if it.get('class') and 'text-main' in it['class']:
                new_html += '<h4>' + it.decode_contents() + '</h4>'
            else:
                new_html += '<p>' + it.decode_contents() + '</p>'
        n = 0.0
        for it in el.find_all(class_='fas'):
            if 'fa-star-half-alt' in it['class']:
                n += 0.5
            elif 'fa-star' in it['class']:
                n += 1.0
        if n > 0:
            new_html += utils.add_stars(n)
        it = el.find('p', string=re.compile(r'Pros', flags=re.I))
        if it:
            new_html += '<div style="font-size:1.05em; font-weight:bold">Pros</div><ul>'
            for it in el.select('p:-soup-contains("Pros") + ul > li'):
                new_html += '<li>' + re.sub(r'^-\s*', '', it.get_text().strip())
            new_html += '</ul>'
        it = el.find('p', string=re.compile(r'Cons', flags=re.I))
        if it:
            new_html += '<div style="font-size:1.05em; font-weight:bold">Cons</div><ul>'
            for it in el.select('p:-soup-contains("Cons") + ul > li'):
                new_html += '<li>' + re.sub(r'^-\s*', '', it.get_text().strip())
            new_html += '</ul>'
        for it in el.find_all('a', class_='buy-button'):
            new_html += utils.add_button(it['href'], it.get_text())
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='review-container'):
        # https://www.shacknews.com/article/140023/xdefiant-review-the-kid-gloves-are-off-in-the-clancyverse
        new_html = '<div>&nbsp;</div>'
        it = el.select('div.nh3 a')
        if it:
            new_html += '<div style="text-align:center; font-size:1.2em; font-weight:bold;">' + str(it[0]) + '</div>'
        it = el.find(class_='score')
        if it:
            new_html += '<div style="text-align:center; font-size:3em; font-weight:bold;">{}</div>'.format(it.get_text())
        for it in el.find_all('div', class_='nh4'):
            it.attrs = {}
            it['style'] = 'font-size:1.1em; font-weight:bold;'
        it = el.find(class_='pros')
        if it:
            new_html += it.decode_contents()
        it = el.find(class_='cons')
        if it:
            new_html += it.decode_contents()
        new_html += '<hr style="width:80%; margin:auto; border-top:1px solid #ccc;"><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='review-wrapper'):
        # https://the5krunner.com/2023/01/11/magene-l508-review-smart-radar-tail-light/
        # https://readysteadycut.com/2024/07/03/beverly-hills-cop-axel-f-review/
        new_html = '<div>&nbsp;</div><div style="margin:8px; padding:8px; border:1px solid #ccc; border-radius:10px;">'
        # img = el.find('img')
        # if img:
        #     new_html += '<img src="{}" style="float:left; margin-right:8px; width:128px;"/>'.format(img['src'])
        #     it.decompose()
        # # else:
        # #     new_html += '<img src="{}/image?width=24&height=24&color=none" style="float:left; margin-right:8px;"/>'.format(config.server)
        # new_html += '<div style="overflow:hidden;">'

        it = el.find(class_='review-title')
        if it:
            title = re.sub(r'[⭐\s]+', ' ', it.get_text().strip())
            new_html += '<div style="text-align:center; font-size:1.2em; font-weight:bold;">' + title + '</div>'

        # if img:
        #     new_html += '</div><div style="clear:left;">&nbsp;</div>'

        it = el.find('span', class_='review-total-box')
        if it:
            new_html += '<div style="text-align:center; font-size:3em; font-weight:bold;">' + it.get_text().strip() + '</div>'
            n = -1
            m = re.search(r'^([\d\.]+)', it.get_text().strip())
            if m:
                n = float(m.group(1))
            else:
                it = el.find(class_='review-result')
                if it and it.get('style'):
                    m = re.search(r'width:\s?(\d+)', it['style'])
                    if m:
                        n = int(m.group(1)) / 20
            if n > 0:
                new_html += utils.add_stars(n)

        for it in el.find_all(class_='review-point'):
            it.decompose()

        it = el.find(class_='review-list')
        if it:
            new_html += '<table style="width:100%; border-collapse:collapse;">'
            for li in it.find_all('li'):
                title = re.sub(r'\s*-\s*[\d\.]+%?$', '', li.span.get_text().strip())
                n = -1
                result = li.find('div', class_='review-result-text')
                if result:
                    m = re.search(r'^(\d+)', result.get_text().strip())
                    n = float(m.group(1))
                else:
                    result = li.find('div', class_='review-result', attrs={"style": re.compile(r'width:\s*\d+')})
                    if result:
                        m = re.search(r'width:\s*(\d+)%', result['style'])
                        n = 5 * float(m.group(1)) / 100
                if n <= 5:
                    # Stars
                    new_html += '<tr style="line-height:1.5em; border-bottom:1px solid #ccc;"><td>' + title + '</td><td>'
                    if n > 0:
                        new_html += utils.add_stars(n, star_size='1em', label='<b>{:.1f}</b>&nbsp;'.format(n))
                    new_html += '</td></tr>'
                else:
                    # Bars
                    new_html += '<tr><td>' + utils.add_bar(title, n, 100) + '</td></tr>'
            new_html += '</table>'

        it = el.select('div.review-desc > p.review-summary-title')
        if it:
            it[0].decompose()
        it = el.find(class_='review-desc')
        if it:
            new_html += it.decode_contents()

        it = el.find(class_='review-pros')
        if it:
            new_html += '<div><strong>Pros</strong></div>' + str(it.find('ul'))

        it = el.find(class_='review-cons')
        if it:
            new_html += '<div><strong>Cons</strong></div>' + str(it.find('ul'))

        it = el.find('ul', class_='review-links')
        if it:
            new_html += '<div><strong>Links</strong></div>' + str(it)
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
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

    for el in soup.find_all(class_='score-box'):
        # https://www.psu.com/reviews/star-wars-bounty-hunter-review-ps5/
        new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; background-color:#ccc; border-radius:10px;">'
        it = el.find(class_='score')
        if it:
            new_html += '<div style="flex:1; min-width:256px; padding:8px; text-align:center;"><h3>Score</h3><div style="font-size:3em; font-weight:bold;">' + it.get_text().strip() + '</div></div>'
        it = el.select('div.cell:has(> h3.entry-title)')
        if it:
            new_html += '<div style="flex:2; min-width:256px; padding:8px;">' + it[-1].decode_contents() + '</div>'
        new_html += '</div><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='post-wrap-review'):
        # https://eftm.com/2024/02/roborock-q8-max-robot-vacuum-fully-featured-more-affordable-and-on-sale-from-today-242331
        new_html = ''
        it = el.find(class_='review-title')
        if it:
            new_html += it.decode_contents()
        new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:center;">'
        it = el.find(class_='review-summary-score-box')
        if it:
            new_html += '<div style="flex:1; min-width:256px;"><div style="font-size:2em; font-weight:bold; text-align:center;">{}</div></div>'.format(it.get_text())
        it = el.find(class_='review-summary-content')
        if it and it.p:
            title = it.find('strong')
            if title:
                title.name = 'div'
                title['style'] = 'font-weight:bold;'
            new_html += '<div style="flex:2; min-width:256px;">' + it.decode_contents() + '</div>'
        new_html += '</div>'
        if el.find(class_='review-breakdowns'):
            new_html += '<div style="width:90%; margin-right:auto; margin-left:auto; margin-right:auto; padding:10px;">'
            for it in el.find_all(class_='review-breakdown'):
                title = it.find(class_='review-breakdown-title').get_text()
                score = it.find(class_='score-text').get_text().strip('%')
                pct = int(score)
                if pct >= 50:
                    new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p>{}</p><p>{}%</p></div>'.format(pct, 100 - pct, title, pct)
                else:
                    new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p>{}</p><p>{}%</p></div>'.format(100 - pct, pct, title, pct)
            new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='xer-review-container'):
        # https://xboxera.com/2024/06/05/destiny-2-the-final-shape-campaign-review/
        new_html = ''
        it = el.find(class_='xer-score')
        if it:
            new_html += '<div style="text-align:center; font-size:1.5em; font-weight:bold;">' + it.get_text() + '</div>'
        it = el.find(class_='xer-scorelabel')
        if it:
            new_html += '<div style="text-align:center; font-size:1.2em; font-weight:bold;">' + it.get_text() + '</div>'
        new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.find(class_='xer-image-preview')
        if it:
            new_html += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%;"/></div>'.format(it.img['src'])
        it = el.find(class_='xer-proscons')
        if it:
            new_html += '<div style="flex:2; min-width:256px;">' + it.decode_contents() + '</div>'
        new_html += '</div>'
        if el.find(class_='xer-review-footer'):
            new_html += '<table style="border-collapse:collapse;">'
            for row in el.select('section.xer-review-footer > div.xer-row > div.xer-col-50 > div.xer-row'):
                new_html += '<tr style="border-bottom:1px solid #ccc;">'
                for col in row.find_all(class_='xer-col-50'):
                    new_html += '<td>' + col.decode_contents() + '</td>'
                new_html += '</tr>'
            new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='movie-summary'):
        # https://filmthreat.com/reviews/star-wars-the-acolyte-season-1/
        new_html = ''
        it = el.find(class_='summary-title')
        if it:
            new_html += '<h3 style="text-align:center;">' + it.get_text() + '</h3>'
            it.decompose()
        it = el.find(class_='summary-rating')
        if it:
            new_html += '<div style="text-align:center; font-size:1.5em; font-weight:bold;">' + it.get_text() + '</div>'
            it.decompose()
        it = el.find(class_='summary-quote')
        if it:
            new_html += '<h3 style="text-align:center;">' + it.get_text() + '</h3>'
        new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.find(class_='summary-image')
        if it:
            new_html += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%;"/></div>'.format(it.img['src'])
        it = el.find(class_='inner')
        if it:
            new_html += '<div style="flex:2; min-width:256px;">' + it.decode_contents() + '</div>'
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='vw-review__summary'):
        # https://www.gizchina.com/2023/10/16/zimablade-review/
        new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:center;">'
        it = el.find(class_='vw-review__total')
        if it:
            if it.find(class_='vw-post-review-stars'):
                score = it.find(class_='vw-post-review-stars').get_text().strip()
            elif it.find(class_='vw-review__dial'):
                score = it.find(class_='vw-review__dial').get('value')
            else:
                score = ''
            new_html += '<div style="flex:1; min-width:256px;"><div style="font-size:2em; font-weight:bold; text-align:center;">{}</div></div>'.format(score)
        it = el.find(class_='vw-review__review-summary')
        if it:
            new_html += '<div style="flex:2; min-width:256px;">' + it.decode_contents() + '</div>'
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='vw-review__items'):
        # https://www.gizchina.com/2023/10/16/zimablade-review/
        new_html = '<div style="width:90%; margin-right:auto; margin-left:auto; margin-right:auto; padding:10px;">'
        for it in el.find_all(class_='vw-review__item'):
            title = it.select('.vw-review__item-title > span')[0].get_text()
            if it.find(class_='vw-post-review-stars'):
                score = it.find(class_='vw-post-review-stars').get_text().strip()
            elif it.find(class_='vw-review__item-title-score'):
                score = it.find(class_='vw-review__item-title-score').get_text().strip()
                if score.endswith('%'):
                    score = int(score.strip('%')) / 10
            elif it.find(class_='vw-review__item-score-bar'):
                score = it.find(class_='vw-review__item-score-bar')
                m = re.search(r'width:\s*(\d+)', score['style'])
                score = int(m.group(1)) / 10
            else:
                score = '0'
            pct = float(score) * 10
            if pct >= 50:
                new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p>{}</p><p>{}</p></div>'.format(pct, 100 - pct, title, score)
            else:
                new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p>{}</p><p>{}</p></div>'.format(100 - pct, pct, title, score)
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('table', class_='td-review'):
        # https://punchdrunkcritics.com/2024/07/review-beverly-hills-cop-axel-f/
        new_html = ''
        it = el.find('td', class_='td-review-desc')
        if it:
            new_html += '<div style="text-align:center; font-size:1.1em; font-weight:bold;">' + it.get_text().strip() + '</div>'
        it = el.find('div', class_='td-review-final-score')
        if it:
            new_html += '<div style="text-align:center; font-size:3em; font-weight:bold;">' + it.get_text().strip() + '</div>'
        if el.find('td', class_='td-review-stars'):
            new_html += '<div style="text-align:center; color:gold; font-size:2em;">'
            for it in el.select('td.td-review-stars > i.td-icon-star'):
                new_html += '★'
            for it in el.select('td.td-review-stars > i.td-icon-star-half'):
                new_html += '<div style="display:inline-block; position:relative; margin:0 auto; text-align:center;"><div style="display:inline-block; background:linear-gradient(to right, gold 50%, transparent 50%); background-clip:text; -webkit-text-fill-color:transparent;">★</div><div style="position:absolute; top:0; width:100%">☆</div></div>'
            for it in el.select('td.td-review-stars > i.td-icon-star-empty'):
                new_html += '☆'
            new_html += '</div>'
        it = el.select('td.td-review-summary > span.block-title')
        if it:
            it[0].decompose()
        it = el.find('td', class_='td-review-summary')
        if it and it.get_text().strip():
            new_html += '<div style="width:90%; margins:auto;">' + it.decode_contents() + '</div>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled td-review in ' + item['url'])

    for el in soup.select('div:has(> div:-soup-contains("The Final Grade"))'):
        # https://www.nintendojo.com/reviews/review-animal-well-switch
        new_html = '<h3>The Final Grade</h3><blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;">'
        it = el.find('img', attrs={"src": re.compile(r'editorsChoice_long\.png')})
        if it:
            new_html += '<div><span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span></div>'
        it = el.find(attrs={"style": re.compile(r'reviewScoreBGWide\.jpg')})
        if it:
            m = re.search(r'^([^<]+)', it.decode_contents())
            if m:
                new_html += '<div style="font-size:3em; font-weight:bold; color:red;">' + m.group(1).strip() + '</div>'
                if it.span:
                    new_html += '<div style="color:red;">' + it.span.get_text() + '</div>'
            it.decompose()
        for it in el.find_all(attrs={"style": re.compile(r'float:\s?left')}):
            it.attrs = {}
            new_html += str(it)
        new_html += '</blockquote>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

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
        el.replace_with(new_el)

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
        el.replace_with(new_el)

    for el in soup.find_all(class_=['trusted-score', 'badges-score-container']):
        new_html = ''
        it = el.find(class_='trusted-score-label')
        if it:
            new_html += '<h2>' + it.get_text() + '</h2>'
        new_html += '<div style="font-size:3em; color:red; text-align:center;">'
        for it in el.find_all('img', class_='rating-star'):
            if it.get('data-src'):
                if 'fullstar.svg' in it['data-src']:
                    new_html += '★'
                elif 'halfstar.svg' in it['data-src']:
                    # new_html += '½'
                    new_html += '<div style="display:inline-block; position:relative; margin:0 auto; text-align:center;"><div style="display:inline-block; background:linear-gradient(to right, red 50%, white 50%); background-clip:text; -webkit-text-fill-color:transparent;">★</div><div style="position:absolute; top:0; width:100%">☆</div></div>'
                elif 'emptystar.svg' in it['data-src']:
                    new_html += '☆'
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('span', class_='key-feature-label'):
        el['style'] = 'font-weight:bold;'
        el.insert_after(soup.new_tag('br'))

    for el in soup.find_all(class_='icon-content-wrapper'):
        el['style'] = 'line-height:2em;'
        it = el.find(class_='icon-text')
        if it:
            it.name = 'span'
            it['style'] = 'font-weight:bold;'
        for it in el.find_all('p'):
            it.unwrap()

    for el in soup.find_all(class_=['spec-comparison', 'test-comparison']):
        new_html = ''
        it = el.find(class_='comparison-title')
        if it:
            new_html += '<h2>' + it.get_text() + '</h2>'
        new_html += '<table style="width:100%; border-collapse:collapse;">'
        it = el.find(class_='table-cell-data-value', attrs={"data-field": "name"})
        if it:
            new_html += '<tr style="line-height:2em; border-bottom:1pt solid black;"><th></th><th style="text-align:left;">{}</th></tr>'.format(it.get_text())
        for i, it in enumerate(el.find_all(class_='table-cell-data-title')):
            if i % 2 == 0:
                new_html += '<tr style="line-height:2em; border-bottom:1pt solid black; background-color:#555;">'
            else:
                new_html += '<tr style="line-height:2em; border-bottom:1pt solid black;">'
            new_html += '<td style="white-space:nowrap; padding:0 8px 0 8px;">{}</td>'.format(it.get_text())
            val = el.find(class_='table-cell-data-value', attrs={"data-field": it['data-field']})
            if val:
                new_html += '<td style="padding:0 8px 0 8px;">{}</td></tr>'.format(val.get_text())
            else:
                new_html += '<td style="padding:0 8px 0 8px;">{}</td></tr>'
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='lets-review-block__wrap'):
        # https://primeaudio.org/arpegear-hane-review/
        # https://press-start.com.au/reviews/xbox-series-x-reviews/2023/05/22/planet-of-lana-review/
        new_html = '<div style="border:1px solid black; border-radius:10px; padding:8px; margin:8px;">'
        it = soup.find('script', attrs={"type": "application/ld+json"})
        if it:
            ld_json = json.loads(it.string)
            #utils.write_file(ld_json, './debug/ld_json.json')
            new_html += '<div style="text-align:center;"><span style="font-size:2em; font-weight:bold;">{}</span> / {}</div>'.format(ld_json['review']['reviewRating']['ratingValue'], ld_json['review']['reviewRating']['bestRating'])
        it = el.find(class_='lets-review-block__conclusion')
        if it:
            new_html += '<div style="padding:1em 0 1em 0;"><em>{}</em></div>'.format(it.get_text())
        if el.find(class_='lets-review-block__proscons'):
            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            new_html += '<div style="flex:1; min-width:256px;"><div style="font-weight:bold;">Positives</div><ul style=\'list-style-type:"➕&nbsp;"\'>'
            for it in el.find_all(class_='lets-review-block__pro'):
                new_html += '<li>' + it.get_text() + '</li>'
            new_html += '</ul></div><div style="flex:1; min-width:256px;"><div style="font-weight:bold;">Negatives</div><ul style=\'list-style-type:"➖&nbsp;"\'>'
            for it in el.find_all(class_='lets-review-block__con'):
                new_html += '<li>' + it.get_text() + '</li>'
            new_html += '</ul></div></div>'
        new_html += '</div><div>&nbsp;</div>'
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
            score = it.get_text().strip()
            new_html += '<div style="text-align:center; line-height:2.5em;"><span style="font-weight:bold; vertical-align:middle;">Rating: </span><span style="font-size:2em; font-weight:bold; vertical-align:middle;">{}</span></div>'.format(score)
        else:
            score = ''
        if score and el.find(class_='rank-math-review-star'):
            new_html += utils.add_stars(float(score))
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

    for el in soup.find_all('span', class_=re.compile('fa-star')):
        if 'fa-star' in el['class']:
            el.string = '★'
            if 'checked' not in el['class']:
                el['style'] = 'color:#ccc;'
        elif 'fa-star-o' in el['class']:
            el.string += '☆'
        elif 'fa-star-half' in el['class'] or 'fa-star-half-empty' in el['class']:
            #el.string += '½'
            new_html = '<div style="display:inline-block; position:relative; margin:0 auto; text-align:center;"><div style="display:inline-block; background:linear-gradient(to right, red 50%, transparent 50%); background-clip:text; -webkit-text-fill-color:transparent;">★</div><div style="position:absolute; top:0; width:100%">☆</div></div>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

    for el in soup.find_all('div', class_='review-info-section'):
        # https://www.expertreviews.co.uk/smartwatches/1418577/huawei-watch-ultimate-review
        new_html = ''
        if el.find(class_='score-overall-info'):
            new_html += '<div style="font-size:1.1em; font-weight:bold;">'
            it = el.select('div.score-overall-info > div.info-item-label')
            if it:
                new_html += it[0].get_text().strip() + '&nbsp;'
            for it in el.select('div.score-overall-info > div.score-overall > span.score-icon > img'):
                if 'star-full.svg' in it['src']:
                    new_html += '★'
                else:
                    new_html += '☆'
            new_html += '</div>'
        if el.find(class_='price-info'):
            new_html += '<p>'
            it = el.select('div.price-info > div.info-item-label')
            if it:
                new_html += it[0].decode_contents()
            it = el.select('div.price-info > span.info')
            if it:
                new_html += it[0].decode_contents()
            new_html += '</p>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

    for el in soup.find_all('div', class_='review-pros-cons-section'):
        # https://www.expertreviews.co.uk/smartwatches/1418577/huawei-watch-ultimate-review
        new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.select('div.pros-column > ul')
        if it:
            new_html += '<div style="flex:1; min-width:256px;"><div style="font-weight:bold;">Pros</div>' + str(it[0]) + '</div>'
        it = el.select('div.cons-column > ul')
        if it:
            new_html += '<div style="flex:1; min-width:256px;"><div style="font-weight:bold;">Cons</div>' + str(it[0]) + '</div>'
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('section', class_='block-two-column-boxes'):
        # https://www.the-ambient.com/reviews/dyson-gen5detect-cordless-vacuum-review/
        new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        for col in el.find_all(class_='col'):
            new_html += '<div style="flex:1; min-width:256px;">'
            it = col.find(class_='col-header')
            if it:
                # new_html += it.decode_contents()
                new_html += '<div style="font-weight:bold;">' + it.get_text() + '</div>'
            it = col.find(class_='col-content')
            if it:
                new_html += it.decode_contents()
            new_html += '</div>'
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('section', class_='review-summary'):
        # https://www.the-ambient.com/reviews/dyson-gen5detect-cordless-vacuum-review/
        new_html = '<div style="background:#ccc; border-radius:10px; padding:10px;">'
        if el.find('div', class_='star-rating'):
            n = len(el.select('div.star-rating > div.full-stars > i.fa-star')) + 0.5 * len(el.select('div.star-rating > div.full-stars > i.fa-star-half'))
            new_html += utils.add_stars(n, star_color='black')
            el.find('div', class_='star-rating').decompose()
        new_html += el.decode_contents()
        new_html += '</div><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='star-rating'):
        # https://www.rogerebert.com/reviews/deadpool-and-wolverine-2024
        n = len(el.find_all(class_='icon-star-full')) + 0.5 * len(el.find_all(class_='icon-star-half'))
        new_html = utils.add_stars(n, no_empty=True)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='spoilers'):
        # https://www.rogerebert.com/reviews/deadpool-and-wolverine-2024
        el['style'] = 'font-size:1.2em; font-weight:bold; color:red; text-align:center; line-height:2em;'
        it = el.find('span', class_='icon-warning')
        if it:
            it.string = '⚠'

    for el in soup.select('div:has(> svg:has(> use[href="#730b1bf98edbef68"]))'):
        # https://www.independent.co.uk/arts-entertainment/music/reviews/billie-eilish-hit-me-hard-and-soft-review-b2546074.html
        n = len(el.find_all('use', href='#730b1bf98edbef68'))
        new_html = utils.add_stars(n, star_color='red')
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('i', class_='fa-star'):
        if 'fa-solid' in el['class']:
            el.string = '★'
            el.name = 'span'
        elif 'fa-regular' in el['class'] or 'fa-light' in el['class'] or 'fa-thin' in el['class']:
            el.string = '☆'
            el.name = 'span'
        else:
            logger.warning('unhandled fa-star icon in ' + item['url'])

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

    for el in soup.find_all(class_='in-content-module', attrs={"data-module-type": "book"}):
        # https://www.nytimes.com/athletic/5735473/2024/08/31/caitlin-clark-fever-angel-reese-sky-wnba-playoffs/
        new_html = '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
        it = el.find('img')
        if it:
            new_html += '<div style="flex:1; min-width:128px; max-width:160px;">'
            if it.parent and it.parent.name == 'a':
                new_html += '<a href="{}"><img src="{}" style="width:100%;"/></a>'.format(it.parent['href'], it['src'])
            else:
                new_html += '<img src="{}" style="width:100%;"/>'.format(it['src'])
            new_html += '</div>'
        new_html += '<div style="flex:2; min-width:256px;">'
        it = el.find('a', class_='in-content-module-headline')
        if it:
            new_html += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(it['href'], it.get_text())
        it = el.find('p', class_='in-content-module-intro-copy')
        if it:
            it.attrs = {}
            it['style'] = 'font-size:0.9em;'
            new_html += str(it)
        it = el.find('a', class_='in-content-module-cta')
        if it:
            new_html += '<div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(it['href'], it.get_text())
        new_html += '</div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_=['et-box', 'factfile', 'snrsInfobox']):
        el.attrs = {}
        el.name = 'blockquote'
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
        for it in el.find_all(class_=['snrsInfoboxContainer', 'snrsInfoboxSubContainer']):
            it.unwrap()

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

    for el in soup.find_all(id='fact_check_rating_container'):
        # https://www.snopes.com/fact-check/photo-bill-gates-at-paris-olympics/
        new_html = '<div>&nbsp;</div>'
        it = el.select('.claim_wrapper > .wrapper_title')
        if it:
            new_html += '<div style="font-size:1.1em; font-weight:bold;">' + it[0].get_text().strip() + '</div>'
        it = el.select('.claim_wrapper > .claim_cont')
        if it:
            new_html += '<p style="margin-left:1em;">' + it[0].decode_contents() + '</p>'
        it = el.select('.rating_wrapper > .wrapper_title')
        if it:
            new_html += '<div style="font-size:1.1em; font-weight:bold;">' + it[0].get_text().strip() + '</div>'
        if el.find(class_='rating_wrapper'):
            new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:center; justify-content:center;">'
            it = el.select('.rating_wrapper > a.rating_link_wrapper')
            if it:
                link = it[0]['href']
                it = el.select('.rating_wrapper > a.rating_link_wrapper > .rating_img_wrap > img')
                if it:
                    new_html += '<div style="flex:1; min-width:160px; max-width:180px; padding:10px;"><a href="{}"><img src="{}" style="width:160px;"/></a></div>'.format(link, it[0]['data-src'])
                it = el.select('.rating_wrapper > a.rating_link_wrapper > .rating_title_wrap')
                if it:
                    new_html += '<div style="flex:1; min-width:256px;"><div style="font-size:1.5em; font-weight:bold;"><a href="{}" style="text-decoration:none;">{}</a></div></div>'.format(link, it[0].contents[0].strip())
            new_html += '</div><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

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
            if links:
                new_html = utils.add_embed(links[-1]['href'])
            else:
                it = el.find(class_='wp-block-embed__wrapper')
                if it:
                    link = it.get_text().strip()
                    if link.startswith('https://twitter.com') or link.startswith('https://x.com'):
                        new_html = utils.add_embed(link)
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

    for el in soup.find_all(class_='cli-embed'):
        # https://www.huffpost.com/entry/supreme-court-decision-grants-pass_n_6632586ce4b05f96b016c567
        new_html = ''
        if el.find(class_='connatix-player'):
            it = el.find('script')
            video_url = 'https://vid.connatix.com/pid-'
            # print(it.string)
            m = re.search(r'playerId.*?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', it.string)
            video_url += m.group(1)
            m = re.search(r'mediaId:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"', it.string)
            video_url += '/' + m.group(1)
            if not utils.url_exists(video_url + '/playlist.m3u8'):
                # TODO: which #_media.bin
                # revision # or version id?
                media_bin = utils.get_url_html(video_url + '/2_media.bin')
                if not media_bin:
                    media_bin = utils.get_url_html(video_url + '/3_media.bin')
                if media_bin:
                    m = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', media_bin)
                    if m:
                        # always last?
                        video_url += '/mmid-' + m[-1]
            video_url += '/playlist.m3u8'
            poster = utils.clean_url(el.img['src'])
            if 'img.connatix.com' in poster:
                poster = 'https://wsrv.nl/?url=' + quote_plus(poster)
            new_html = utils.add_video(video_url, 'application/x-mpegURL', poster)
        elif el.find('blockquote', class_='twitter-tweet'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        else:
            it = el.find('iframe', id=re.compile(r'youtube-embed'))
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled cli-embed in ' + item['url'])

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
        elif el.get('style') and 'border' in el['style']:
            # https://gamesfray.com/apple-effectively-kills-numerous-browser-games-in-the-eu-unprecedented-slap-in-the-face-of-tech-regulation/
            el.attrs = {}
            el['style'] = 'border:1px solid black; padding:1em;'
        elif el.find(class_='wp-block-media-text'):
            # https://signalcleveland.org/cleveland-families-who-lost-loved-ones-to-homicide-reclaim-their-stories/
            it = el.find(class_='wp-block-group__inner-container')
            if it:
                it.unwrap()
            if 'has-background' in el['class']:
                el.attrs = {}
                el['style'] = 'background-color:#ccc; margin:8px; padding:8px;'
            for elm in el.find_all(class_='wp-block-media-text'):
                new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                it = elm.find(class_='wp-block-media-text__media')
                if it and it.img:
                    new_html += '<div style="flex:1; min-width:256px; margin:auto;"><img src="" style="width:100%;" />' + add_image(it, None, base_url, site_json, decompose=False) + '</div>'
                it = elm.find(class_='wp-block-media-text__content')
                if it:
                    new_html += '<div style="flex:2; min-width:256px; margin:auto;"><img src="" style="width:100%;" />' + it.decode_contents() + '</div>'
                new_html += '</div>'
                new_el = BeautifulSoup(new_html, 'html.parser')
                elm.replace_with(new_el)
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
            it = el.find_parent('div', class_='wp-caption')
            if it:
                it.replace_with(new_el)
            else:
                el.replace_with(new_el)
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

    for el in soup.find_all(class_='medium-insert-embeds'):
        new_html = ''
        it = el.find('blockquote', class_='instagram-media')
        if it:
            new_html = utils.add_embed(it['data-instgrm-permalink'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled medium-insert-embeds in ' + item['url'])

    for el in soup.find_all(class_='video-summary-wrap'):
        it = el.find('a', attrs={"rel": "playerjs"})
        if it:
            new_html = utils.add_embed(it['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
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
            mpx_html = utils.get_url_html(el.iframe['data-mpx-src'])
            if mpx_html:
                mpx_soup = BeautifulSoup(mpx_html, 'lxml')
                it = mpx_soup.find('link', attrs={"type": "application/smil+xml"})
                if it:
                    video_src = utils.get_redirect_url(it['href'])
                    if re.search('.mp4', video_src, flags=re.I):
                        video_type = 'video/mp4'
                    else:
                        video_type = 'application/x-mpegURL'
                    it = mpx_soup.find('meta', attrs={"property": "og:image"})
                    if it:
                        poster = it['content']
                    else:
                        poster = ''
                    it = mpx_soup.find('meta', attrs={"property": "og:description"})
                    if it:
                        caption = it['content']
                    else:
                        caption = ''
                new_html = utils.add_video(video_src, video_type, poster, caption)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
        if not new_html:
            logger.warning('unhandled nbcsports-video-wrapper in ' + item['url'])

    for el in soup.find_all(class_='nyp-video-player'):
        new_html = ''
        it = el.find(id=re.compile(r'jw-player'))
        if it:
            m = re.search(r'jw-player-[^-]+-([^-]+)', it['id'])
            if m:
                new_html = utils.add_embed('https://cdn.jwplayer.com/v2/media/' + m.group(1))
        else:
            it = el.find(attrs={"data-exs-config": True})
            if it and it.get('data-exs-config'):
                video_json = json.loads(it['data-exs-config'])
                if video_json.get('videos') and video_json['videos'].get('sources'):
                    new_html = utils.add_embed(video_json['videos']['sources'][0]['source'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled nyp-video-player in ' + item['url'])

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

    for el in soup.find_all('green-video'):
        new_html = ''
        api_url = 'https://media-api-prod.greenvideo.io/api/v1/content/' + el['content-id']
        it = soup.find('script', attrs={"src": re.compile(r'greenvideo'), "data-license-key": True})
        if it:
            headers = {
                "x-dl8-licensekey": it['data-license-key']
            }
            video_json = utils.get_url_json(api_url, headers=headers)
            if video_json:
                utils.write_file(video_json, './debug/video.json')
                video = next((it for it in video_json['result']['videoRenditions'] if it['type'] == 'application/x-mpegurl'), None)
                if not video:
                    video = video_json['result']['videoRenditions'][0]
                new_html = utils.add_video(video['src'], video['type'], video_json['result']['poster'][0]['src'], video_json['result']['title'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent:
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled green-video in ' + item['url'])

    for el in soup.find_all(class_='wp-block-fuel-fuelshortcode'):
        it = el.find(class_='fuel-title-heading')
        if it:
            caption = it.get_text().strip()
        else:
            caption = ''
        it = el.find('fuel-video')
        if it:
            new_html = utils.add_video(it['video-url'], 'application/x-mpegURL', it.get('data-poster-image'), caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled wp-block-fuel-fuelshortcode in ' + item['url'])

    for el in soup.find_all('script', attrs={"src": re.compile(r'newsource-embed-prd\.ns\.cnn\.com/videos/embed')}):
        new_html = ''
        video_json = utils.get_url_json('https://newsource-video-player-api.ns.cnn.com/api/v1/faveVideo/?id={}&edition=single&customer={}&env=prd'.format(el['data-player-data'], el['data-newsource-publisher']))
        if video_json:
            video_src = ''
            video = next((it for it in video_json['files'] if it['bitrate'] == 'default_mp4'), None)
            if video:
                video_src = video['fileUri']
                video_type = 'video/mp4'
            else:
                video_src = video_json['files'][0]['fileUri']
                video_type = 'application/x-mpegURL'
            caption = ''
            if video_json.get('headline'):
                caption = video_json['headline']
            elif video_json.get('description'):
                caption = video_json['description']
            else:
                caption = ''
            img = next((it for it in video_json['images'] if it['name'] == 'big'), None)
            if img:
                poster = img['uri']
            else:
                poster = video_json['images'][0]['uri']
            new_html = utils.add_video(video_src, video_type, poster, caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'p':
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled cnn video embed in ' + item['url'])

    for el in soup.find_all(class_='embedly-plugin'):
        # https://www.smithsonianmag.com/history/everyone-should-know-rickwood-field-alabama-park-baseball-legends-history-180984524/
        it = el.find(class_='watch-on-youtube')
        if it and it.a:
            new_html = utils.add_embed(it.a['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'figure':
                el.parent.replace_with(new_el)
            else:
                el.replace_with(new_el)
        else:
            logger.warning('unhandled embedly-plugin in ' + item['url'])

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

    for el in soup.find_all(class_='list-sc-item'):
        # https://people.com/team-usa-mens-basketball-olympics-wives-and-girlfriends-8679906
        new_html = ''
        if el.find(class_='mntl-sc-block-heading'):
            new_html += '<h3>'
            it = el.find(class_='content-list-number__item-number')
            if it:
                new_html += it.get_text().strip() + ' | '
            it = el.find(class_='mntl-sc-block-heading__text')
            if it:
                new_html += it.get_text().strip()
            new_html += '</h3>'
        it = el.find('figure', class_='mntl-sc-block-image')
        if it:
            new_html += add_image(it, it, base_url, site_json)
        for it in el.find_all('a', class_='mm-trx-commerce-button'):
            new_html += utils.add_button(it['href'], it.get_text().strip())
        for it in el.find_all('p', recursive=False):
            new_html += str(it)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled list-sc-item in ' + item['url'])

    for el in soup.find_all(class_='mm-trx-sc-block-commerce'):
        new_html = ''
        for it in el.find_all('a', class_='mm-trx-commerce-button'):
            new_html += utils.add_button(it['href'], it.get_text().strip())
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled mm-trx-sc-block-commerce in ' + item['url'])

    for el in soup.find_all(class_='slideshow_slide'):
        # https://www.yardbarker.com/entertainment/articles/20_bands_wed_like_to_see_reunite/s1__40995793
        new_html = ''
        if el.find(class_='slideshow_title_bar'):
            new_html += '<h3>'
            it = el.select('div.slideshow_title_bar > div.slide_count')
            if it and it[0].get_text().strip():
                m = re.search(r'^\d+', it[0].get_text().strip())
                if m:
                    new_html += '{}. '.format(m.group(0))
            it = el.select('div.slideshow_title_bar > h2.slide_title')
            if it and it[0].get_text().strip():
                new_html += it[0].get_text().strip()
            new_html += '</h3>'
        it = el.find(class_='slide_credit')
        if it:
            caption = it.get_text().strip()
        else:
            caption = ''
        it = el.find(class_='slideshow_image_div')
        if it:
            new_html += add_image(it, it, base_url, site_json, caption)
        it = el.find(class_='slide_description')
        if it:
            new_html += it.decode_contents()
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_=['gallery', 'tiled-gallery', 'wp-block-gallery', 'wp-block-jetpack-tiled-gallery', 'wp-block-coblocks-gallery-collage', 'article-slideshow', 'wp-block-jetpack-slideshow', 'ess-gallery-container', 'inline-slideshow', 'list-gallery', 'carousel-basic', 'm-carousel', 'media-carousel', 'multiple-images', 'image-pair', 'undark-image-caption', 'photo-layout', 'rslides', 'banner-grid-wrapper', 'slider-wrapper', 'slideshow-wrapper', 'article-gallery', 'article__gallery', 'article__images', 'pictures', 'swiper-wrapper', 'whtGallery']) + soup.select('div.ars-lightbox:has(img.ars-gallery-image)'):
        # print(el['class'])
        if el.name == None:
            continue
        gallery_caption = ''
        if set(['gallery', 'tiled-gallery', 'wp-block-gallery', 'wp-block-jetpack-tiled-gallery']).intersection(el['class']):
            images = None
            if el.find('ul', class_='gallery-wrap'):
                images = el.find_all('li')
                add_caption = True
            elif 'wp-block-jetpack-tiled-gallery' in el['class']:
                # https://rogersmovienation.com/2023/05/22/movie-review-disney-remakes-the-little-mermaid-but-is-it-music-to-me/
                images = el.find_all(class_='tiled-gallery__item')
                add_caption = True
            elif 'has-nested-images' in el['class']:
                images = el.find_all('figure')
                add_caption = True
            elif el.find(class_='gallery-item'):
                images = el.find_all(class_='gallery-item')
                add_caption = True
            elif 'tiled-gallery' in el['class']:
                images = el.find_all(class_='tiled-gallery-item')
                add_caption = True
            elif el.name == 'aside':
                # https://www.nintendolife.com/news/2024/09/miniatures-is-a-bite-sized-short-story-collection-that-will-make-you-feel
                images = el.select('a > img')
                add_caption = True
                it = el.find('figcaption', recursive=False)
                if it:
                    gallery_caption = it.decode_contents()
            if not images:
                images = [img for img in el.find_all('img') if (img.get('class') and 'carousel-thumbnail' not in img['class'])]
                add_caption = False
        elif 'wp-block-coblocks-gallery-collage' in el['class']:
            # https://awasteof.coffee/2020/11/07/how-i-learned-to-stop-worrying-and-love-the-bripe/
            images = el.select('li.wp-block-coblocks-gallery-collage__item:has(> figure)')
            add_caption = True
        elif set(['article-slideshow', 'wp-block-jetpack-slideshow']).intersection(el['class']):
            images = el.find_all('li')
            add_caption = True
        elif 'ess-gallery-container' in el['class']:
            # https://www.essence.com/entertainment/beyonce-dubai-atlantis-the-royal-grand-reveal-performance/
            images = el.find_all(class_='gallery-slide')
            add_caption = True
        elif 'inline-slideshow' in el['class']:
            # https://trendeepro.com/like-emily-ratajkowski-im-a-mom-who-takes-my-baby-to-work/
            images = el.find_all(class_='inline-slideshow__slide')
            add_caption = True
        elif 'list-gallery' in el['class']:
            images = el.find_all(class_='ami-gallery-item')
            add_caption = True
        elif 'carousel-basic' in el['class']:
            # https://whyy.org/?p=644617
            images = el.find_all(class_='carousel-cell')
            add_caption = False
        elif 'm-carousel' in el['class']:
            # https://www.digitaltrends.com/mobile/oneplus-11-review/
            images = el.find_all('figure', class_='m-carousel--content')
            add_caption = True
        elif 'media-carousel' in el['class']:
            # https://prospect.org/blogs-and-newsletters/tap/2024-07-12-paler-shade-of-gray/
            images = el.find_all(id=re.compile(r'ms-slide-'))
            # images = el.find_all(class_=['media', 'youtube'], recursive=False)
            add_caption = True
        elif 'multiple-images' in el['class']:
            # https://themarkup.org/news/2023/02/08/how-big-tech-rewrote-the-nations-first-cellphone-repair-law
            images = el.find_all('li', class_='multiple-images__item')
            add_caption = False
        elif 'image-pair' in el['class']:
            images = el.find_all('figure', class_='image-pair__figure')
            add_caption = True
        elif 'undark-image-caption' in el['class']:
            # https://undark.org/2023/02/22/how-an-early-warning-radar-could-prevent-future-pandemics/
            images = el.find_all(class_='cell')
            add_caption = True
        elif 'photo-layout' in el['class']:
            # https://news.harvard.edu/gazette/story/2023/05/inspired-by-mother-bacow-decided-he-wasnt-done-being-a-leader/
            images = el.find_all(class_='photo-layout__image-wrap')
            if not images:
                images = el.find_all(class_='photo-layout__image')
            add_caption = False
        elif 'rslides' in el['class']:
            # https://www.timesofisrael.com/idf-warns-civilians-to-leave-northern-gaza-as-ground-invasion-looms/
            images = el.find_all('li')
            add_caption = True
        elif 'banner-grid-wrapper' in el['class']:
            # https://www.audubonart.com/extinct-species-in-audubons-birds-of-america/
            images = el.find_all(class_='img')
            add_caption = True
        elif 'pictures' in el['class']:
            # https://www.nintendolife.com/reviews/switch-eshop/jackbox-naughty-pack
            images = el.select('a:has(> img)')
            add_caption = True
        elif 'slider-wrapper' in el['class']:
            # https://www.audubonart.com/the-inclusion-of-foreign-avian-species-in-goulds-birds-of-europe/
            images = el.find_all(class_='img')
            add_caption = True
        elif 'slideshow-wrapper' in el['class']:
            # https://www.smithsonianmag.com/travel/the-15-best-small-towns-to-visit-in-2024-180984472/
            images = el.find_all(class_='slide')
            add_caption = True
        elif 'swiper-wrapper' in el['class']:
            # https://www.smithsonianmag.com/travel/the-15-best-small-towns-to-visit-in-2024-180984472/
            images = el.find_all(class_='swiper-slide')
            add_caption = True
        elif 'article-gallery' in el['class']:
            # https://medicalxpress.com/news/2024-06-drug-therapy-apnea.html
            images = el.find_all(class_='article-img')
            add_caption = True
        elif 'article__gallery' in el['class']:
            # https://www.themoscowtimes.com/2024/07/08/in-photos-okhmatdyt-childrens-hospital-after-russian-strike-a85643
            images = el.find_all(class_='article__gallery__item')
            add_caption = True
        elif 'article__images' in el['class']:
            # https://www.themoscowtimes.com/2024/06/17/one-name-one-life-one-plaque-russian-project-installs-reminders-of-soviet-repressions-a85393
            images = el.find_all(class_='slider__slide')
            add_caption = True
        elif 'whtGallery' in el['class']:
            # https://android.gadgethacks.com/how-to/see-passwords-for-wi-fi-networks-youve-connected-your-android-device-0160995/
            images = el.find_all('figure')
            add_caption = True
        elif 'ars-lightbox' in el['class']:
            images = el.find_all(class_='ars-lightbox-item')
            add_caption = True
        gallery_parent = el.find_parent('div', id=re.compile(r'attachment_\d'))
        if not gallery_parent:
            gallery_parent = el.find_parent('p')
            if not gallery_parent:
                gallery_parent = el
        if len(images) == 1:
            if images[0].find(class_='youtube'):
                # https://prospect.org/videos/2024-07-12-prospect-weekly-roundup/
                it = images[0].find(attrs={"data-src": True})
                if it:
                    new_html = utils.add_embed(it['data-src'])
                else:
                    logger.warning('unhandled youtube media in ' + item['url'])
            elif images[0].iframe:
                new_html = utils.add_embed(images[0].iframe['src'])
            else:
                new_html = add_image(images[0], gallery_parent, base_url, site_json, add_caption=True, decompose=False, insert=False)
        else:
            new_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            n = len(images) - 1
            for i, img in enumerate(images):
                # print(i, img)
                if i < n:
                    new_html += '<div style="flex:1; min-width:360px;">' + add_image(img, gallery_parent, base_url, site_json, add_caption=add_caption, decompose=False, insert=False, gallery=True, n=i+1) + '</div>'
                else:
                    new_html += '<div style="flex:1; min-width:360px;">' + add_image(img, gallery_parent, base_url, site_json, add_caption=True, decompose=False, insert=False, gallery=True, n=i+1) + '</div>'
                # img.decompose()
            new_html += '</div>'
            if gallery_caption:
                new_html += '<div><small>' + gallery_caption + '</small></div>'
            new_html += '<div>&nbsp;</div>'
            for it in gallery_parent.find_all(['style', 'br']):
                it.decompose()
            new_el = BeautifulSoup(new_html, 'html.parser')
            gallery_images = []
            for it in new_el.find_all('figure'):
                thumb = resize_image(it.img['src'], site_json, width=600)
                if it.figcaption:
                    caption = it.figcaption.small.decode_contents()
                else:
                    caption = ''
                gallery_images.append({"src": it.img['src'], "caption": caption, "thumb": thumb})
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + new_html
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_before(new_el)
        el.decompose()
        if gallery_parent.name != None:
            if not (gallery_parent.name == 'p' and gallery_parent.get_text().strip()):
                gallery_parent.decompose()

    for el in soup.find_all(id='photo-gallery-container'):
        new_html = ''
        if 'ksl.com' in item['url'] and page_soup:
            # https://www.ksl.com/article/51097087/harris-says-she-would-never-interfere-in-fed-independence
            it = page_soup.find('script',string=re.compile(r'ksl/gallery'))
            if it:
                print(it.string)
                m = re.search(r'const images = Object\((.*?)\)\.map', it.string)
                if m:
                    gallery_json = json.loads(m.group(1))
                    gallery_images = []
                    new_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                    for image in gallery_json:
                        captions = []
                        if image.get('caption'):
                            captions.append(image['caption'])
                        if image.get('credit'):
                            captions.append(image['credit'])
                        new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(image['source'], ''.join(captions), link=image['source']) + '</div>'
                        gallery_images.append({"src": image['source'], "caption": ''.join(captions), "thumb": image['source']})
                gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + new_html
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled photo-gallery-container in ' + item['url'])

    for el in soup.find_all(class_='pbslideshow-wrapper'):
        # https://www.playstationlifestyle.net/2023/01/23/forspoken-review-ps5-worth-playing
        new_html = ''
        if not page_soup:
            page_html = utils.get_url_html(item['url'])
            if page_html:
                page_soup = BeautifulSoup(page_html, 'lxml')
        if page_soup:
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
            slideshow_html = utils.get_url_html('{}/index.php?action=get_slideshow&slideshow_id={}&template=desktopview&imagetag=&query={}'.format(base_url, slideshow_id, quote_plus(query)))
            if slideshow_html:
                # utils.write_file(slideshow_html, './debug/slideshow.html')
                slideshow_soup = BeautifulSoup(slideshow_html, 'html.parser')
                images = slideshow_soup.find_all(class_='pbslideshow-slider-item')
                desc = slideshow_soup.find_all(class_='pbslideshow-description-inner')
                new_html = '<h2>Gallery</h2>'
                for i, it in enumerate(images):
                    if desc[i].get_text().strip():
                        new_html += utils.add_image(resize_image(it['data-pbslazyurl'], site_json), desc=str(desc[i]))
                    else:
                        new_html += utils.add_image(resize_image(it['data-pbslazyurl'], site_json))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)

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

    for el in soup.find_all('section', class_='wp-block-uagb-section'):
        # https://neo-trans.blog/2024/02/16/haslams-keep-options-open-for-brook-park-site/
        img = el.find(class_='wp-block-image')
        if img:
            captions = []
            for it in el.select('div.uagb-section__inner-wrap > p'):
                captions.append(it.decode_contents())
            add_image(img, el, base_url, site_json, caption=' | '.join(captions))
            el.decompose()
        else:
            logger.warning('unhandled wp-block-uagb-section in ' + item['url'])

    for el in soup.find_all(class_='dc-image-container'):
        if el.parent and el.parent.name == 'p':
            it = el.parent.find_next_sibling('p')
            if it and it.find(class_='wp-caption'):
                caption = it.find(class_='wp-caption').decode_contents()
                it.decompose()
            else:
                caption = ''
            add_image(el, el.parent, base_url, site_json, caption=caption)
        else:
            logger.warning('unhandled dc-image-container in ' + item['url'])

    for el in soup.find_all(['figure', 'div'], id=re.compile(r'media-\d+|attachment_\d+')):
        add_image(el, None, base_url, site_json)

    for el in soup.select('figure:has( blockquote)'):
        if 'class' in el and 'wp-block-pullquote' in el['class']:
            continue
        if 'independent.co.uk' in item['url']:
            # https://www.independent.co.uk/arts-entertainment/films/features/pulp-fiction-quentin-tarantino-30-anniversary-b2585762.html
            if el.find('svg'):
                it = el.select('div > blockquote')
                if it:
                    quote = it[0].decode_contents()
                    it = el.select('div:has(> blockquote) + div')
                    if it:
                        author = it[0].get_text().strip()
                    else:
                        author = ''
                    new_html = utils.add_pullquote(quote, author)
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.replace_with(new_el)
        # https://www.independent.co.uk/life-style/paris-2024-olympics-celebrities-b2586619.html
        add_image(el, el, base_url, site_json)

    for el in soup.select('div.image.align-none'):
        # https://www.independent.co.uk/life-style/paris-2024-olympics-celebrities-b2586619.html
        add_image(el, el, base_url, site_json)

    for el in soup.find_all('figure', class_=['bodyimg', 'picture']):
        add_image(el, None, base_url, site_json)

    # for el in soup.find_all('a', attrs={"data-type": "inarticle-image-block"}):
    #     # https://www.carscoops.com/2024/08/2025-chevrolet-traverse-gains-luxurious-high-country-trim/
    #     add_image(el, el, base_url, site_json)

    for el in soup.select('figure:has( a[rel*="wp-att"])'):
        # https://japannews.yomiuri.co.jp/news-services/afp-jiji/20240818-205740/
        add_image(el, el, base_url, site_json)

    for el in soup.find_all(class_='widget'):
        if 'widget--type-image' in el['class']:
            add_image(el.figure, el, base_url, site_json)
        else:
            new_html = ''
            if 'widget--type-tweet' in el['class']:
                it = soup.find(class_='widget__tweet')
                new_html = utils.add_embed('https://twitter.com/__/status/' + it['data-tweet-id'])
            elif 'widget--type-instagram' in el['class']:
                new_html = utils.add_embed(el['data-oembed-url'])
            elif 'widget--type-flourish' in el['class']:
                it = el.find(class_='flourish-embed')
                new_html = utils.add_embed('https://flo.uri.sh/{}/embed?auto=1'.format(it['data-src'].split('?')[0]))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled widget in ' + item['url'])

    for el in soup.find_all(class_=re.compile(r'article[-_]+image|article-grid-width-image|bp-embedded-image|br-image|c-figure|c-image|cli-image|captioned-image-container|custom-image-block|embed--image|entry-image|featured-media-img|featured-image|img-responsive|r-img-caption|gb-block-image|img-wrap|pom-image-wrap|post-content-image|block-coreImage|wp-block-image|wp-block-media|wp-block-ups-image|wp-caption|wp-post-image|wp-image-\d+|img-container|inline_image|sc-block-image|-insert-image|max-w-img-|image--shortcode|(?<!-)custom-caption')):
        # print(el.parent.name)
        if el.name != None:
            if not (el.name == 'p' and 'wp-caption-text' in el['class']):
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

    for el in soup.select('figure:has(> img[data-image])'):
        add_image(el, el, base_url, site_json)

    for el in soup.find_all(class_='media-wrapper'):
        # Used on macstories.net
        new_html = ''
        if 'subscribe-podcast-cta' in el['class']:
            el.decompose()
        elif 'audio-player' in el['class']:
            it = el.find('source')
            if it:
                new_html = '<div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Play</a></span></div>'.format(it['src'], config.server)
        elif 'video-autoplay' in el['class']:
            caption = ''
            poster = ''
            video_src = ''
            video_type = ''
            it = el.find('caption')
            if it:
                caption = it.get_text().strip()
            it = el.find('video')
            if it:
                if it.get('poster'):
                    poster = it['poster']
                if it.get('src'):
                    video_src = it['src']
            it = el.find('source', attrs={"type": "video/mp4"})
            if it:
                video_src = it['src']
                if it.get('type'):
                    video_type = it['type']
            else:
                it = el.find('source')
                if it:
                    video_src = it['src']
                    if it.get('type'):
                        video_type = it['type']
            if video_src:
                if not video_type:
                    if '.mp4' in video_src:
                        video_type = 'video/mp4'
                    elif '.webm' in video_src:
                        video_type = 'video/webm'
                    elif '.ogv' in video_src:
                        video_type = 'video/ogg'
                    else:
                        video_type = 'application/x-mpegURL'
                new_html += utils.add_video(video_src, video_type, poster, caption)
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
        elif len(el['class']) == 1 and el.find('img'):
            add_image(el, el, base_url, site_json, decompose=True)
            continue
        else:
            logger.warning('unhandled media-wrapper class {}'.format(el['class']))
            # print(el)
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
        new_html = ''
        if 'jwplayer' in el['class'] and el.get('id') and el['id'].startswith('jwp'):
            if not page_soup:
                page_html = utils.get_url_html(item['url'])
                if page_html:
                    page_soup = BeautifulSoup(page_html, 'lxml')
            if page_soup:
                it = page_soup.find('script', string=re.compile(r'tmbi_video_settings'))
                if it:
                    i = it.string.find('{')
                    j = it.string.rfind('}') + 1
                    video_json = json.loads(it.string[i:j])
                    video = next((it for it in video_json['video_players'] if it['player_id'] == el['id']), None)
                    if video:
                        new_html = utils.add_embed('https://content.jwplatform.com/players/{}.html'.format(video['video_id']))
        else:
            # https://stratechery.com/2022/microsoft-full-circle/
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
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

    for el in soup.find_all(class_='jw-adthrive-wrap'):
        # https://www.mediaite.com/politics/maga-clad-woman-tries-to-convince-interviewer-the-us-government-controlled-the-hurricanes-to-hurt-trump/
        it = el.find('meta', attrs={"itemprop": "contentUrl"})
        if it:
            new_html = utils.add_embed(it['content'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled jw-adthrive-wrap in ' + item['url'])

    for el in soup.find_all('figure', attrs={"itemtype": "http://schema.org/VideoObject"}):
        new_html = ''
        video = el.find('video')
        if video:
            it = el.find('meta', attrs={"itemprop": "name"})
            if it:
                caption = it['content']
            else:
                caption = ''
            new_html = utils.add_video(video.source['src'], video.source['type'], video.get('poster'), caption)
        else:
            video = el.find('iframe')
            if video and video.get('src'):
                new_html = utils.add_embed(video['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled VideoObject in ' + item['url'])

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
            audio_src = '{}/videojs?src={}&type=audio%2Fmpeg'.format(config.server, quote_plus(audio_src))
            it = el.find(class_='wp-element-caption')
            if it:
                caption = it.get_text().strip()
            else:
                caption = 'Play'
            new_html = '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}" target="_blank"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}" target="_blank">{2}</a></span></div>'.format(audio_src, config.server, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled wp-block-audio in ' + item['url'])

    for el in soup.find_all('pba-play-button'):
        new_html = ''
        if el['media-type'] == 'audio':
            # https://www.wabe.org/indian-americans-in-georgia-are-starting-to-exercise-their-political-power/
            new_html = utils.add_audio(el['source'], '', el['title'], el['story-link'], el['show'], el['show-link'], '', el['time'], show_poster=False)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled pba-play-button in ' + item['url'])

    for el in soup.find_all(id='playht-iframe-wrapper'):
        # https://vsquare.org/leaked-files-putin-troll-factory-russia-european-elections-factory-of-fakes/
        new_html = ''
        if el.iframe:
            embed_html = utils.get_url_html(el.iframe['src'])
            if embed_html:
                utils.write_file(embed_html, './debug/audio.html')
                m = re.search(r'"audio_src_file":"([^"]+)"', embed_html)
                if m:
                    new_html = utils.add_audio(m.group(1), '', 'Listen to this article', el.iframe['src'], '', '', '', '', show_poster=False)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled playht-iframe-wrapper in ' + item['url'])

    for el in soup.find_all('a', class_='playlistitem'):
        it = el.find(class_='audio-label')
        if it:
            caption = it.get_text().strip()
        else:
            caption = 'Listen'
        it = el.find(class_='duration')
        if it:
            caption += ' ({})'.format(it.get_text().strip())
        audio_src = '{}/videojs?src={}&type=audio%2Fmpeg'.format(config.server, quote_plus(el['href']))
        new_html = '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}" target="_blank"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}" target="_blank">{2}</a></span></div>'.format(audio_src, config.server, caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='podcast'):
        # https://www.quantamagazine.org/are-robots-about-to-level-up-20240814/
        new_html = ''
        it = el.find('a', href=re.compile(r'podcasts\.apple\.com'))
        if not it:
            it = el.find('a', href=re.compile(r'open\.spotify\.com'))
        if it:
            new_html = utils.add_embed(it['href'])
        # poster = '{}/image?&width=256&overlay=audio'.format(config.server)
        # it = el.find('img')
        # if it:
        #     poster += '&url=' + quote_plus(it['src'])
        # it = el.find('a', href=re.compile(r'\.mp3'))
        # if it:
        #     audio_src = utils.get_redirect_url(it['href'])
        # else:
        #     audio_src = item['url']
        # it = el.find('h4')
        # if it:
        #     title = '<h3>{}</h3>'.format(it.get_text())
        # else:
        #     title = ''
        # new_html = '<div style="text-align:center;">{}<a href="{}"><img src="{}"/></a></div>'.format(title, audio_src, poster)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled podcast in ' + item['url'])

    for el in soup.find_all('figure', class_='youtube'):
        new_html = utils.add_embed(el['data-src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='embed-youtube'):
        new_html = ''
        if el.iframe:
            if el.iframe.get('src'):
                new_html = utils.add_embed(el.iframe['src'])
            elif el.iframe.get('data-src'):
                new_html = utils.add_embed(el.iframe['data-src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled embed-youtube in ' + item['url'])

    for el in soup.find_all(class_='acf--code'):
        # https://www.quantamagazine.org/the-hidden-world-of-electrostatic-ecology-20240930/
        new_html = ''
        video = el.select('div.acf-media video')
        if video and video[0].get('src'):
            captions = []
            it = el.select('figcaption div.caption > p')
            if it:
                captions.append(it[0].decode_contents())
            it = el.select('figcaption div.attribution > p')
            if it:
                captions.append(it[0].decode_contents())
            new_html = utils.add_video(video[0]['src'], 'video/mp4', video[0].get('poster'), ' | '.join(captions), use_videojs=True)
        elif el.find('style', string=re.compile(r'newsletter')):
            el.decompose()
            continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled acf--code in ' + item['url'])

    for el in soup.find_all(class_='video-container'):
        new_html = ''
        if el.find(class_='js-video') or 'pmYTPlayerContainer' in el['class']:
            new_html = utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(el['id']))
        elif el.find('video-js'):
            it = el.find('video-js')
            video_url = 'https://players.brightcove.net/{}/{}_default/index.html'.format(it['data-account'], it['data-player'])
            if it.get('data-video-id'):
                video_url += '?videoId=' + it['data-video-id']
            elif it.get('data-playlist-id'):
                video_url += '?playlistId=' + it['data-playlist-id']
            else:
                video_url = ''
            if video_url:
                new_html = utils.add_embed(video_url)
        else:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
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
            logger.warning('unhandled jwplayer_placeholder in ' + item['url'])

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

    for el in soup.find_all('div', class_='br-video__cont'):
        # https://www.sportsnet.ca/nhl/article/evaluating-whether-the-leafs-top-players-eat-up-too-much-power-play-time/
        new_html = ''
        it = el.find(class_='br-video-ssg')
        if it and site_json.get('bc_account_id'):
            m = re.search(r'videoID=(\d+)', it.string)
            if m:
                video_id = m.group(1)
                account_id = site_json['bc_account_id']
                m = re.search(r'playerID=(\w+)', it.string)
                if m:
                    player_id = m.group(1)
                else:
                    player_id = ''
                new_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(account_id, player_id, video_id))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled br-video__cont in ' + item['url'])

    for el in soup.find_all('div', class_='sn-video-container'):
        # https://www.sportsnet.ca/nhl/video/hurricanes-necas-turns-on-the-jets-from-his-own-end-and-snipes-one-past-georgiev/
        new_html = ''
        it = soup.find('script', class_='bc-embed-script', string=re.compile(el['id']))
        if it:
            m = re.search(r'bc_videos:\s+(\d+)', it.string)
            if m:
                video_id = m.group(1)
                m = re.search(r'bc_account_id:\s+"([^"]+)"', it.string)
                if m:
                    account_id = m.group(1)
                elif site_json.get('bc_account_id'):
                    account_id = site_json['bc_account_id']
                m = re.search(r'bc_player_id:\s+"([^"]+)"', it.string)
                if m:
                    player_id = m.group(1)
                elif site_json.get('bc_account_id'):
                    player_id = ''
                new_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(account_id, player_id, video_id), {"add_summary": True})
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled sn-video-container in ' + item['url'])

    for el in soup.find_all(class_='video-holder'):
        new_html = ''
        if el.get('data-type') and el['data-type'] == 'youtube':
            it = el.find('source')
            if it:
                if it['src'].startswith('http'):
                    new_html = utils.add_embed(it['src'])
                elif it['src'].startswith('//'):
                    new_html = utils.add_embed('https:' + it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled video-holder in ' + item['url'])

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

    for el in soup.find_all('video-js'):
        video_url = 'https://players.brightcove.net/{}/{}_default/index.html?'.format(el['data-account'], el['data-player'])
        if el.get('data-video-id'):
            video_url += '?videoId=' + el['data-video-id']
        elif el.get('data-playlist-id'):
            video_url += '?playlistId=' + el['data-playlist-id']
        else:
            logger.warning('unhandled video-js embed in ' + item['url'])
            video_url = ''
        if video_url:
            new_html = utils.add_embed(video_url)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el_parent = el
            while el_parent.parent.parent:
                el_parent = el_parent.parent
            el_parent.replace_with(new_el)

    for el in soup.find_all('et_pb_video'):
        # https://filmfeeder.co.uk/film-reviews/inside-out-2-2024-dir-kelsey-mann
        video_src = re.sub(r'”|″', '', el['src'])
        new_html = utils.add_embed(video_src)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(['et_pb_image', 'et_pb_fullwidth_image']):
        # https://filmfeeder.co.uk/film-reviews/inside-out-2-2024-dir-kelsey-mann
        img_src = re.sub(r'”|″', '', el['src'])
        # if el.get('title_text'):
        #     caption = re.sub(r'”|″', '', el['title_text'])
        # else:
        #     caption = ''
        if el.get('url'):
            link = re.sub(r'”|″', '', el['url'])
        else:
            link = ''
        new_html = utils.add_image(img_src, link=link)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_=['mntl-sc-block-embed', 'mntl-sc-block-universal-embed']):
        # https://people.com/youtubers-brooklyn-and-bailey-mcknight-reveal-the-moment-pregnant-brooklyn-told-her-twin-she-s-expecting-8680783
        new_html = ''
        it = el.find('iframe')
        if it:
            if it.get('data-src'):
                if it['data-src'].startswith('/embed'):
                    params = parse_qs(urlsplit(it['data-src']).query)
                    if params.get('url'):
                        new_html = utils.add_embed(params['url'][0])
                else:
                    new_html = utils.add_embed(it['data-src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled mntl-sc-block-universal-embed in ' + item['url'])

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
        if el.get('class') and 'wp-embedded-content' in el['class']:
            for it in soup.find_all('blockquote', class_='wp-embedded-content'):
                if it.a and utils.clean_url(it.a['href']) in utils.clean_url(el['src']):
                    el.decompose()
        if el.name != None:
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

                if el.get('data-lazy-src'):
                    src = el['data-lazy-src']
                elif el.get('data-src'):
                    src = el['data-src']
                elif el.get('src'):
                    src = el['src']
                else:
                    src = ''
                if src:
                    if not re.search(r'amazon-adsystem\.com', src):
                        new_html = utils.add_embed(src)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el_parent.insert_after(new_el)
            el_parent.decompose()
        elif el.name != None:
            logger.warning('unhandled iframe in ' + item['url'])

    for el in soup.find_all(class_=['twitter-tweet', 'twitter-video', 'twitter-quote']):
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(attrs={"data-initial-classes": "twitter-tweet"}):
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.replace_with(new_el)

    for el in soup.select('div.twitter-post:has(> amp-twitter)'):
        # https://www.independent.co.uk/news/world/americas/us-politics/nikki-haley-kamala-harris-dei-attacks-b2586647.html
        it = el.find('amp-twitter')
        new_html = utils.add_embed('https://twitter.com/__/status/' + it['data-tweetid'], save_debug=True)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='tiktok-embed'):
        new_el = BeautifulSoup(utils.add_embed(el['cite']), 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('amp-tiktok'):
        new_el = BeautifulSoup(utils.add_embed(el['data-src']), 'html.parser')
        if el.parent and el.parent.name == 'div':
            el.parent.replace_with(new_el)
        else:
            el.replace_with(new_el)

    for el in soup.find_all(id=re.compile(r'buzzsprout-player-\d+')):
        it = soup.find('script', src=re.compile(el['id']))
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled buzzsprout-player in ' + item['url'])

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

    for el in soup.find_all(class_='newsroomBlockQuoteContainer'):
        quote = ''
        it = el.find(class_='newsroomBlockQuoteQuoteContainer')
        if it:
            for i, p in enumerate(it.find_all('p')):
                if i > 0:
                    quote += '<br/><br/>'
                quote += p.decode_contents()
        if quote:
            it = el.find(class_='newsroomBlockQuoteAuthorContainer')
            if it:
                author = it.get_text()
            else:
                author = ''
            new_html = utils.add_pullquote(quote, author)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled newsroomBlockQuoteContainer in ' + item['url'])

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

    for el in soup.find_all(class_=['post__aside__pullquote', 'article__quote', 'pullquote', 'pull-quote', 'wp-block-pullquote', 'simplePullQuote', 'undark-pull-quote']):
        if el.name == None:
            continue
        if el.blockquote:
            el.blockquote.unwrap()
        it = el.find('cite')
        if it:
            author = it.get_text()
            it.decompose()
        else:
            it = el.find(class_='pullquote-attribution')
            if it:
                author = it.get_text()
            else:
                author = ''
        it = el.find(class_='soundcite')
        if it:
            it.decompose()
        it = el.find(class_=['article__quote-copy', 'blockquote-text', 'pullquote-quote', 'mb1'])
        if it:
            new_html = utils.add_pullquote(it.decode_contents(), author)
        else:
            it = el.find(class_='undark-quote')
            if it:
                new_html = utils.add_pullquote(it.get_text().strip(), author)
            else:
                new_html = utils.add_pullquote(el.decode_contents(), author)
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el.find_parent('section', class_='article-pullquote')
        if it:
            it.replace_with(new_el)
        else:
            el.replace_with(new_el)

    for el in soup.find_all(class_='article-pull-quote'):
        quote = el.find(class_='text')
        if quote:
            it = el.find(class_='author')
            if it:
                author = it.get_text()
            else:
                author = ''
            new_html = utils.add_pullquote(quote.decode_contents(), author)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled article-pull-quote in ' + item['url'])

    for el in soup.find_all('blockquote', class_='cli-pullquote'):
        quote = el.find(class_='cli-pullquote__quote')
        if quote:
            it = el.find(class_='cli-pullquote__attribution')
            if it:
                author = it.get_text()
            else:
                author = ''
            new_html = utils.add_pullquote(quote.decode_contents(), author)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled cli-pullquote in ' + item['url'])

    for el in soup.find_all(class_='pull-quote-container'):
        it = el.find(class_='br-pull_quote_text')
        if it:
            new_html = utils.add_pullquote(it.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled pull-quote-container in ' + item['url'])

    for el in soup.find_all(class_='section--quotation-block'):
        # https://glorioussport.com/articles/kristina-makushenko-underwater-dancer-interview/
        it = el.find('blockquote')
        if it:
            new_html = '<h1 style="text-align:center; text-transform:uppercase;">“' + it.get_text().strip() + '”</h1>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled section--quotation-blockr in ' + item['url'])

    for el in soup.find_all('blockquote'):
        if el.name == None or re.search(r'^Embedded content from', el.get_text()):
            # Likely a nested blockquote which won't get styled
            continue
        new_html = ''
        if el.get('class'):
            if 'instagram-media' in el['class']:
                new_html = utils.add_embed(el['data-instgrm-permalink'])
            elif 'text-post-media' in el['class']:
                new_html = utils.add_embed(el['data-text-post-permalink'])
            elif 'reddit-embed-bq' in el['class'] or 'reddit-card' in el['class']:
                it = el.find('a')
                if it:
                    new_html = utils.add_embed(it['href'])
            elif 'wp-embedded-content' in el['class']:
                if soup.find('iframe', class_='wp-embedded-content'):
                    el.decompose()
                elif el.a:
                    new_html = utils.add_embed(el.a['href'])
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
                    elif 'blockquote_default' in site_json:
                        if site_json['blockquote_default'] == 'pullquote':
                            new_html = utils.add_pullquote(quote, author) + '<div>&nbsp;</div>'
                        else:
                            new_html = utils.add_blockquote(quote, False)
                    else:
                        new_html = utils.add_blockquote(quote)
                else:
                    new_html = '<div>&nbsp;</div>'
        if not new_html and el.get_text().strip():
            if el.get('id') and re.search(r'blockquote\d', el['id']):
                it = el.find_previous_sibling()
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
                    it = el.find_previous('p')
                    if it and it.get_text().strip().endswith(':'):
                        new_html = utils.add_blockquote(el.decode_contents(), False)
                    else:
                        if site_json and 'blockquote_default' in site_json:
                            if site_json['blockquote_default'] == 'pullquote':
                                new_html = utils.add_pullquote(el.decode_contents())
                            else:
                                new_html = utils.add_blockquote(el.decode_contents())
                        else:
                            new_html = utils.add_blockquote(el.decode_contents())
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        elif el.name != None:
            logger.warning('unhandled blockquote in ' + item['url'])

    for el in soup.find_all(class_=re.compile(r'textbox\d')):
        el.name = 'blockquote'
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all(class_='aside-wide'):
        el.name = 'blockquote'
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.select('p:has(> cite)'):
        el.name = 'blockquote'
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all(class_='info-box'):
        new_html = '<table style="margin:1.5em 10px;"><tr><td style="font-size:3em; font-weight:bold;">ⓘ</td><td style="font-style:italic; padding:8px;">{}</td></tr></table>'.format(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

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

    for el in soup.find_all(class_='abstract'):
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

    for el in soup.find_all(class_='media-element'):
        it = el.find('img', class_='media-element-image')
        if it:
            new_html = '<table style="border:1px solid black; border-radius:10px;"><tr><td style="width:128px;"><img src="{}" style="width:100%;"></td><td style="padding-left:8px; font-size:0.9em;">'.format(it['src'])
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
        if el['src'].startswith('//'):
            el['src'] = 'https:' + el['src']
        else:
            el['src'] = base_url + el['src']

    for el in soup.find_all('a', href=re.compile(r'go\.redirectingat\.com/')):
        el['href'] = utils.get_redirect_url(el['href'])

    for el in soup.find_all(class_='embeded-carousel'):
        new_html = ''
        if el.find(class_='owl-carousel'):
            # https://www.tasteofhome.com/article/what-are-paczki/
            new_html += '<div style="display:flex; flex-wrap:wrap; justify-content:center; gap:1em;">'
            for it in el.find_all(class_='embedded-carousel-content'):
                new_html += '<div style="flex:1; min-width:180px; max-width:256px; border:1px solid black; border-radius:10px;">'
                link = it.find('a', class_='embeded-card-title')
                img = it.find('img')
                if img:
                    new_html += '<div><a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;"/></a></div>'.format(link['href'], img['src'])
                new_html += '<div style="text-align:center; font-weight:bold;">{}</div>'.format(link.get_text())
                new_html += '<div style="text-align:center; line-height:3em;"><span style="padding:0.4em; background-color:#d62329;"><a href="{}" style="color:white; text-decoration:none;">Shop now</a></span></div>'.format(link['href'])
                new_html += '</div>'
            new_html += '</div>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embedded-carousel in ' + item['url'])

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

    # Remaining un-classed figures & images
    for el in soup.select('figure:has(img)'):
        if el.name == None:
            continue
        if el.attrs == {} or (el.get('class') and 'align-' in '|'.join(el['class'])):
            add_image(el, None, base_url, site_json)

    #for el in soup.find_all('img', class_='post-image'):
    for el in soup.find_all(lambda tag: tag.name == 'img' and
            (('class' in tag.attrs and ('post-image' in tag.attrs['class'] or 'flex-fullWidthImage' in tag.attrs['class'])) or
             ('alt' in tag.attrs) or ('width' in tag.attrs) or ('decoding' in tag.attrs))):
        if el.name == None:
            continue
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

    for el in soup.select('center:has( > img)'):
        add_image(el, None, base_url, site_json)

    for el in soup.find_all(['aside', 'ins', 'link', 'meta', 'noscript', 'script', 'style']):
        el.decompose()

    if not item.get('_image'):
        el = soup.find('img')
        if el:
            # print(el)
            item['_image'] = el['src']

    if site_json and site_json.get('clear_attrs'):
        for el in soup.find_all(id=True):
            del el['id']
        for el in soup.find_all(class_=True):
            del el['class']

    try:
        content_html = re.sub(r'</(figure|table)>\s*<(div|figure|table|/li)', r'</\1><div>&nbsp;</div><\2', soup.encode('iso-8859-1').decode('utf-8'))
    except:
        content_html = re.sub(r'</(figure|table)>\s*<(div|figure|table|/li)', r'</\1><div>&nbsp;</div><\2', str(soup))
    return content_html


def get_content(url, args, site_json, save_debug=False, page_soup=None):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 0 and paths[-1] == 'embed':
        del paths[-1]
        args['embed'] = True

    post = None
    posts_path = ''
    post_url = ''
    if not page_soup and (site_json.get('content') or site_json.get('add_content') or site_json.get('author') or site_json.get('lede_img') or site_json.get('lede_video') or site_json.get('title') or site_json.get('subtitle')):
        page_soup = get_page_soup(url, site_json, save_debug)

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

        if page_soup:
            # print(wpjson_path)
            post_url, post_id = find_post_url(page_soup, wpjson_path + posts_path)
            if post_url:
                # print(post_url)
                post = utils.get_url_json(post_url)

        if not post:
            # Try to determine the post id or slug from the path
            if 'slug' in site_json:
                if site_json['slug'] and isinstance(site_json['slug'], int):
                    if paths[site_json['slug']].isnumeric():
                        post_url = '{}{}/{}'.format(wpjson_path, posts_path, paths[site_json['slug']])
                    else:
                        post_url = '{}{}?slug={}'.format(wpjson_path, posts_path, paths[site_json['slug']])
                    # print(post_url)
                    post = utils.get_url_json(post_url)
            elif len(paths) == 0 and split_url.query and 'p=' in split_url.query:
                query = parse_qs(split_url.query)
                if query.get('p'):
                    post_url = '{}{}/{}'.format(wpjson_path, posts_path, query['p'][0])
                    post = utils.get_url_json(post_url)
            else:
                for it in paths:
                    # print(it)
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
    if not page_soup:
        page_soup = get_page_soup(url, site_json, save_debug)
    if page_soup:
        if save_debug:
            utils.write_file(str(page_soup), './debug/debug.html')
        if 'slug' in site_json:
            if site_json['slug'] and isinstance(site_json['slug'], str) and site_json['slug'] == 'title':
                el = page_soup.find('meta', attrs={"property": "og:title"})
                if el:
                    slug = el['content'].lower().replace('’', '')
                    slug = re.sub(r'\W+', '-', slug)
                    post_url = '{}{}?slug={}'.format(wpjson_path, posts_path, slug)
                    # print(post_url)
        if not post_url:
            el = page_soup.find('link', attrs={"rel": "alternate", "type": "application/json", "href": re.compile(r'wp-json')})
            if el:
                m = re.search(r'/(\d{3,})', el['href'])
                # post_url = el['href']
                post_url = '{}{}/{}'.format(wpjson_path, posts_path, m.group(1))
            else:
                el = page_soup.find('link', attrs={"rel": "shortlink"})
                if el:
                    query = parse_qs(urlsplit(el['href']).query)
                    if query.get('p'):
                        post_url = '{}{}/{}'.format(wpjson_path, posts_path, query['p'][0])
                else:
                    el = page_soup.find('article', attrs={"data-post-id": True})
                    if el:
                        post_url = '{}{}/{}'.format(wpjson_path, posts_path, el['data-post-id'])
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
    if isinstance(post, list):
        return get_post_content(post[0], args, site_json, page_soup, save_debug)
    else:
        return get_post_content(post, args, site_json, page_soup, save_debug)


def find_post_url(page_soup, wpjson_path):
    post_id = ''
    post_url = ''
    # Find the direct wp-json link
    el = page_soup.find('link', attrs={"rel": "alternate", "type": "application/json", "href": re.compile(r'wp-json')})
    if el:
        # post_url = el['href']
        m = re.search(r'/(\d+)', post_url)
        if m:
            post_id = m.group(1)
            post_url = '{}/{}'.format(wpjson_path, post_id)
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
    if site_json.get('content') or site_json.get('add_content') or site_json.get('author') or site_json.get('lede_img') or site_json.get('lede_video') or site_json.get('title') or site_json.get('subtitle'):
        page_soup = get_page_soup(url, site_json, save_debug)

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
            if post_url:
                logger.debug('getting wp_post from ' + post_url)
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
                    logger.debug('getting wp_post from ' + post_url)
                    wp_post = utils.get_url_json(post_url)
                if 'no_slug' not in args and '-' in it and not (site_json.get('exclude_slugs') and it in site_json['exclude_slugs']):
                    # Try path as slug
                    slug = it.split('.')[0]
                    m = re.search(r'-(\d{5,}$)', slug)
                    if m and not (len(m.group(1)) == 8 and m.group(1).startswith('202')):
                        # Check if it contains the post id
                        post_url = '{}/{}'.format(wpjson_path, m.group(1))
                        logger.debug('getting wp_post from ' + post_url)
                        wp_post = utils.get_url_json(post_url)
                    if not wp_post:
                        post_url = '{}?slug={}'.format(wpjson_path, slug)
                        logger.debug('getting wp_post from ' + post_url)
                        wp_post = utils.get_url_json(post_url)
                else:
                    continue
                if wp_post:
                    # Finding by slug returns a list of matches
                    if isinstance(wp_post, list):
                        wp_post = wp_post[0]
                    break

            if not wp_post and not page_soup:
                page_soup = get_page_soup(url, site_json, save_debug)
                if page_soup:
                    # utils.write_file(str(page_soup), './debug/debug.html')
                    post_url, post_id = find_post_url(page_soup, wpjson_path)
                    if post_url:
                        logger.debug('getting wp_post from ' + post_url)
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
    elif wp_post and wp_post.get('yoast_head_json') and wp_post['yoast_head_json'].get('og_title'):
        item['title'] = wp_post['yoast_head_json']['og_title']
    elif wp_post and wp_post.get('title') and wp_post['title'].get('rendered'):
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
    else:
        item['author'] = {"name": split_url.netloc}

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
    elif ld_article and ld_article.get('articleSection') and isinstance(ld_article['articleSection'], list):
        item['tags'] = ld_article['articleSection'].copy()
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

