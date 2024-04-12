import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def render_sections(sections, test_values, test_stats, lab_tests, product_name, heading=2):
    section_html = ''
    for section in sections:
        section_html += '<h{0}>{1}</h{0}>'.format(heading, section['title'])
        if section.get('content'):
            section_html += section['content']
        if section.get('sections'):
            section_html += render_sections(section['sections'], test_values, test_stats, lab_tests, product_name, heading + 1)
        if section.get('images'):
            for image in section['images']:
                if image.get('video_url'):
                    section_html += utils.add_video(image['video_url'], 'video/mp4', image['url'].replace('{SIZE}', 'main'))
                else:
                    section_html += utils.add_image(image['url'].replace('{SIZE}', 'main'))
        if section.get('test_id'):
            id = str(section['test_id'])
            test = lab_tests['tests'][id]
            if test_values.get(id):
                section_html += '<div>&nbsp;</div><table style="border-collapse:collapse;"><tr style="line-height:2em; border-bottom:1pt solid black;"><th colspan="2">Test results &ndash; {}</th></tr>'.format(test['name'])
                section_html += '<tr style="line-height:2em; border-bottom:1pt solid black;"><td>{}</td>'.format(product_name)
                if test_stats.get(id):
                    if test['type'] == 'percent':
                        unit = '%'
                    elif test.get('units'):
                        unit = ' ' + test['units']
                    else:
                        unit = ''
                    section_html += '<td style="padding:0 1em 0 8px;">{}{}</td></tr>'.format(test_values[id], unit)
                    section_html += '<tr style="line-height:2em; border-bottom:1pt solid black;"><td>Average</td><td style="padding:0 1em 0 8px;">{}{}</td></tr>'.format(test_stats[id]['average'], unit)
                else:
                    if test_values[id] == '0':
                        section_html += '<td style="padding:0 1em 0 8px;">No</td></tr>'
                    elif test_values[id] == '1':
                        section_html += '<td style="padding:0 1em 0 8px;">Yes</td></tr>'
                    else:
                        section_html += '<td style="padding:0 1em 0 8px;">{}</td></tr>'.format(test_values[id].title())
                section_html += '</table><div>&nbsp;</div>'
    return section_html


def format_content(content_html):
    soup = BeautifulSoup(content_html, 'html.parser')

    for el in soup.find_all('span', class_='mce-annotation'):
        el.unwrap()

    for el in soup.select('p > img'):
        if el.get('srcset'):
            img_src = utils.image_from_srcset(el['srcset'], 1080)
        else:
            img_src = el['src']
        if img_src.startswith('../..'):
            img_src = img_src.replace('../..', 'https://runrepeat.com')
        new_html = utils.add_image(img_src)
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el.find_parent('p')
        it.insert_after(new_el)
        it.decompose()

    for el in soup.find_all('div', attrs={"data-vue-component": "LocalVideo"}):
        it = el.find('source')
        new_html = utils.add_video(it['src'], it['type'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('div', attrs={"data-vue-component": "ProductsTable"}):
        new_html = '<table style="width:100%; border-collapse:collapse;">'
        headers = json.loads(html.unescape(el['data-headers']))
        new_html += '<tr style="line-height:2em;"><th colspan="{}" style="border:1px solid black;">{}</th></tr>'.format(len(headers), el['data-title'])
        new_html += '<tr style="line-height:2em;">'
        for i, it in enumerate(headers):
            if i == 0:
                new_html += '<th style="border:1px solid black; text-align:left;">'
            else:
                new_html += '<th style="border:1px solid black;">'
            new_html += it + '</th>'
        new_html += '</tr>'
        rows = json.loads(html.unescape(el['data-rows']))
        # if 'marathon' in el['data-title']:
        #     utils.write_file(rows, './debug/data.json')
        for row in rows:
            new_html += '<tr style="line-height:2em;">'
            for i, td in enumerate(row):
                if i == 0:
                    new_html += '<td style="border:1px solid black;">'
                else:
                    new_html += '<td style="border:1px solid black; text-align:center;">'
                for it in td:
                    if it.get('type') and it['type'] == 'score':
                        new_html += '<b style="color:{};">{} {}</b>'.format(it['score_color'].replace('_', ''), it['text'], it['score_text'])
                    elif it.get('url'):
                        new_html += '<a href="{}">{}</a>'.format(it['url'], it['text'])
                    else:
                        if isinstance(it['text'], list):
                            text = []
                            for txt in it['text']:
                                if txt.get('url'):
                                    text.append('<a href="{}">{}</a>'.format(txt['url'], txt['text']))
                                else:
                                    text.append(txt['text'])
                            new_html += ' | '.join(text)
                        else:
                            new_html += it['text']
                new_html += '</td>'
            new_html += '</tr>'
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    return str(soup)


def add_comparison(product_ids, best_text=[]):
    api_url = 'https://api.runrepeat.com/simple-comparison/{}?size=6&same_brand=0&force_color'.format(product_ids[0])
    if len(product_ids) > 1:
        api_url += '&force_product_ids%5B%5D=' + '&force_product_ids%5B%5D='.join(map(str, product_ids))

    comparison = utils.get_url_json(api_url)
    if not comparison:
        return ''

    # utils.write_file(comparison, './debug/comparison.json')

    content_html = '<h2>Comparison</h2><div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse;"><tr style="line-height:2em;"><th style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;"></th>'
    for it in comparison:
        content_html += '<th style="text-align:center; vertical-align:top; padding:8px 8px 0 8px; border:1px solid black;"><img src="{}"/><br/><a href="https://runrepeat.com/{}">{}</a></th>'.format(it['image']['url'].replace('{SIZE}', '250'), it['slug'], it['name'])
    content_html += '</tr>'
    if best_text:
        content_html += '<tr style="line-height:2em;"><td style="white-space:nowrap; padding:0 8px 0 8px; border:1px solid black;"">Best</td>'
        for it in best_text:
            content_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;"><b>{}</b></td>'.format(it)
        content_html += '</tr>'
    n = len(comparison)
    all_keys = []
    for i in range(n):
        all_keys += comparison[i].keys()
    all_keys = sorted(list(set(all_keys)))
    row = 0
    top_keys = ['corescore', 'expert-score', 'users-score', 'ranking', 'popularity', 'price']
    for key in top_keys:
        val = comparison[0][key]
        if key == 'price':
            name = 'Best price'
        else:
            name = val['name']
        if row % 2 == 0:
            content_html += '<tr style="line-height:2em; background-color:#ccc;"><td style="white-space:nowrap; padding:0 8px 0 8px; border:1px solid black;">{}</td>'.format(name)
        else:
            content_html += '<tr style="line-height:2em;"><td style="white-space:nowrap; padding:0 8px 0 8px; border:1px solid black;"">{}</td>'.format(name)
        row += 1
        for i in range(n):
            if val['slug'] == 'corescore':
                content_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;"><span style="font-weight:bold; color:{}">{} {}</span></td>'.format(comparison[i]['score_color'].replace('_', ''), comparison[i][key]['value'], comparison[i]['score_text'])
            elif val['slug'] == 'expert-score':
                content_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">{}</td>'.format(comparison[i][key]['value'])
            elif val['slug'] == 'users-score':
                content_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">{:.0f}<br/>({} votes)</td>'.format(comparison[i][key]['value'], comparison[i]['users_votes_count'])
            elif val['slug'] == 'popularity' or val['slug'] == 'ranking':
                content_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">#{}</td>'.format(comparison[i][key]['value'])
            elif val['slug'] == 'price':
                content_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">{}</td>'.format(comparison[i][key]['formatted'])
    for key in all_keys:
        if key in top_keys:
            continue
        row_html = ''
        row_name = ''
        for i in range(n):
            if key not in comparison[i]:
                key_val = next((it for it in comparison if it.get(key)), None)
                if key_val and isinstance(key_val, dict) and key_val.get('name'):
                    row_html += '<td style="border:1px solid black;"></td>'
                continue
            elif not isinstance(comparison[i][key], dict):
                continue
            key_val = comparison[i][key]
            if isinstance(key_val, dict) and key_val.get('name'):
                row_name = key_val['name']
                if key_val.get('type'):
                    if key_val['type'] == 'bool':
                        if comparison[i][key]['value'] == True:
                            row_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;"><span style="color:green;">✓</span></td>'
                        else:
                            row_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;"><span style="color:red;">𐄂</span></td>'
                    elif key_val['type'] == 'options' or key_val['type'] == 'options-multi':
                        values = []
                        for v in key_val['value']:
                            values.append(v['name'])
                        if values:
                            row_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">{}</td>'.format('<br/>'.join(values))
                        else:
                            row_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">&mdash;</td>'
                    elif key_val['type'] == 'value':
                        row_html += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">' + str(key_val['value'])
                        if key_val.get('units'):
                            row_html += ' ' + key_val['units']
                        row_html += '</td>'
                    else:
                        row_html += '<td style="border:1px solid black;"></td>'
                else:
                    logger.warning('unhandled key value ' + key)
        if row_html:
            if row % 2 == 0:
                content_html += '<tr style="line-height:2em; background-color:#ccc;"><td  style="white-space:nowrap; padding:0 8px 0 8px; border:1px solid black;">{}</td>'.format(row_name)
            else:
                content_html += '<tr style="line-height:2em;"><td  style="white-space:nowrap; padding:0 8px 0 8px; border:1px solid black;">{}</td>'.format(row_name)
            content_html += row_html + '</tr>'
            row += 1
    content_html += '</table></div>'
    return content_html

def get_guide_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = 'https://api.runrepeat.com/api/pages/guide/' + paths[-1]
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    page_meta = api_json['page_meta']
    page_data = api_json['page_data']
    article = page_data['article']

    item = {}
    item['id'] = article['id']
    item['url'] = page_meta['canonical']
    item['title'] = page_meta['title']

    dt = datetime.fromisoformat(article['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article.get('dateModified'):
        dt = datetime.fromisoformat(article['dateModified'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": article['author']['name']}

    item['content_html'] = ''

    if page_data.get('primary_image'):
        item['_image'] = page_data['primary_image']['url'].replace('{SIZE}', 'main')
        item['content_html'] += utils.add_image(item['_image'])
    elif article.get('image'):
        item['_image'] = article['image']['url'].replace('{SIZE}', 'main')
        item['content_html'] += utils.add_image(item['_image'])

    if article.get('description'):
        item['summary'] = article['description']
    elif page_meta.get('description'):
        item['summary'] = page_meta['description']

    content = []
    if article.get('content_1'):
        # Usually intro
        item['content_html'] += format_content(article['content_1'])
        content.append('content_1')

    for key, val in page_data['toc'].items():
        for it in val:
            if 'how-we-test' in it['id']:
                item['content_html'] += format_content(article[key])

    if page_data.get('top_picks'):
        product_ids = []
        best_text = []
        for pick in page_data['top_picks']:
            for product in pick['products']:
                product_ids.append(product['id'])
                best_text.append(re.sub(r'^Best ', '', pick['title']).title())
        item['content_html'] += add_comparison(product_ids, best_text)

        for pick in page_data['top_picks']:
            item['content_html'] += '<h2>{}</h2>'.format(pick['title_long'])
            for product in pick['products']:
                item['content_html'] += '<h3><a href="https://runrepeat.com/{}">{}</a> &ndash; <span style="color:{};">{} {}</span></h3>'.format(product['slug'], product['name'], product['score_color'].replace('_', ''), product['score'], product['score_text'])
                item['content_html'] += utils.add_image(product['image']['url'].replace('{SIZE}', 'main'))
                item['content_html'] += product['description']
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                soup = BeautifulSoup(product['good_bad'], 'html.parser')
                el = soup.find(id='the_good')
                if el:
                    item['content_html'] += '<div style="flex:1; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;">Pros</div><ul style="margin:0;">'
                    item['content_html'] += el.find('ul').decode_contents()
                    item['content_html'] += '</ul></div>'
                el = soup.find(id='the_bad')
                if el:
                    item['content_html'] += '<div style="flex:1; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;">Cons</div><ul style="margin:0;">'
                    item['content_html'] += el.find('ul').decode_contents()
                    item['content_html'] += '</ul></div>'
                item['content_html'] += '</div><div>&nbsp;</div>'
                item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">Offers</div><table style="width:100%; border-collapse:collapse;">'
                for i, offer in enumerate(product['offers']['by_color']['0']):
                    if i == 5:
                        break
                    shop = next((it for it in page_data['shops'] if it['id'] == offer['shop_id']), None)
                    if re.search(r'(adidas|amazon|dsw|ebay|moosejaw|runningwarehouse)\.com', offer['affiliate_link']):
                        link = offer['affiliate_link']
                    else:
                        link = utils.get_redirect_url(offer['affiliate_link'])
                    item['content_html'] += '<tr style="line-height:2em; border-top:1px solid black; border-bottom:1px solid black;">'
                    item['content_html'] += '<td><a href="{}">{}</a></td>'.format(link, shop['name'])
                    item['content_html'] += '<td style="font-size:0.8em;">{}</td>'.format(offer['text'])
                    item['content_html'] += '<td>{}</td>'.format(offer['price_formatted'])
                item['content_html'] += '</table>'

    for key in page_data['toc'].keys():
        if key not in content:
            item['content_html'] += format_content(article[key])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_content(url, args, site_json, save_debug=False):
    if '/guides/' in url:
        return get_guide_content(url, args, site_json, save_debug)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = 'https://api.runrepeat.com/api/pages/from-slug/' + paths[-1]
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    page_meta = api_json['page_meta']
    page_data = api_json['page_data']
    page_content = page_data['content']
    product = page_data['product']

    item = {}
    item['id'] = api_json['entity_id']
    item['url'] = page_meta['canonical']
    item['title'] = page_meta['title']

    dt = datetime.fromisoformat(product['created_at_iso'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if product.get('updated_at_iso'):
        dt = datetime.fromisoformat(product['updated_at_iso'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": page_data['author']['name']}

    item['content_html'] = ''

    if page_content.get('image'):
        item['content_html'] += utils.add_image(page_content['image']['url'].replace('{SIZE}', 'main'))

    item['content_html'] += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
    if page_content.get('intro'):
        item['content_html'] += '<div style="flex:1; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;">Our verdict</div><div>{}</div>'.format(page_content['intro'])
        if page_data.get('rankings') and page_data['rankings'].get('our_texts'):
            item['content_html'] += '<ul style="list-style-position:outside; padding-left:1em;">'
            for it in page_data['rankings']['our_texts']:
                item['content_html'] += '<li>' + it['text']
                if it.get('link'):
                    item['content_html'] += '<a href="{}">{}</a>'.format(it['link'], it['linkText'])
                item['content_html'] += '</li>'
        item['content_html'] += '</div>'

    if product.get('score'):
        item['content_html'] += '<div style="flex:1; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;">Audience verdict</div><div style="font-weight:bold; color:{}">{} {}</div>'.format(product['score_color'].replace('_', ''), product['score'], product['score_text'])
        if page_data.get('rankings') and page_data['rankings'].get('audience_texts'):
            item['content_html'] += '<ul style="list-style-position:outside; padding-left:1em;">'
            for it in page_data['rankings']['audience_texts']:
                item['content_html'] += '<li>' + it['text']
                if it.get('link'):
                    item['content_html'] += '<a href="{}">{}</a>'.format(it['link'], it['linkText'])
                item['content_html'] += '</li>'
        item['content_html'] += '</div>'

    if page_content.get('pros'):
        item['content_html'] += '<div style="flex:1; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;">Pros</div><ul style="margin:0;">'
        for it in page_content['pros']:
            item['content_html'] += '<li>' + it + '</li>'
        item['content_html'] += '</ul></div>'

    if page_content.get('cons'):
        item['content_html'] += '<div style="flex:1; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;">Cons</div><ul style="margin:0;">'
        for it in page_content['cons']:
            item['content_html'] += '<li>' + it + '</li>'
        item['content_html'] += '</ul></div>'
    item['content_html'] += '</div>'

    lab_html = ''
    if page_content.get('lab'):
        lab_html = render_sections(page_content['lab']['sections'], page_content['lab'].get('values'), page_content['lab'].get('stats'), page_data.get('lab_tests'), product['name'])
    if page_content.get('primary'):
        lab_html = page_content['primary']
    if lab_html:
        item['content_html'] += format_content(lab_html)

    if page_content.get('lab') and page_content['lab'].get('values'):
        item['content_html'] += '<h2>Lab test results</h2><div style="overflow-x:auto;"><table style="width:100%; border-collapse:collapse;"><tr style="line-height:2em;"><th style="border:1px solid black;"></th><th style="border:1px solid black;">{}</th><th style="border:1px solid black;">Average</th></tr>'.format(product['name'])
        for section in page_content['lab']['category']['config']['sections']:
            group = page_data['lab_tests']['groups'][str(section['group_id'])]
            item['content_html'] += '<tr style="line-height:2em;"><td colspan="3" style="padding:0 4px 0 4px; border:1px solid black;"><b>{}</b></td></tr>'.format(group['name'])
            for test in section['tests']:
                test_id = str(test['test_id'])
                lab_test = page_data['lab_tests']['tests'][test_id]
                if page_content['lab']['values'].get(test_id):
                    test_value = page_content['lab']['values'][test_id]
                    item['content_html'] += '<tr style="line-height:2em;"><td style="white-space:nowrap; padding:0 16px 0 16px; border:1px solid black;">{}</td>'.format(lab_test['name'])
                    if page_content['lab']['stats'].get(test_id):
                        if lab_test['type'] == 'percent':
                            unit = '%'
                        elif lab_test.get('units'):
                            unit = ' ' + lab_test['units']
                        else:
                            unit = ''
                        item['content_html'] += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">{}{}</td><td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">{}{}</td>'.format(test_value, unit, page_content['lab']['stats'][test_id]['average'], unit)
                    else:
                        if test_value == '0':
                            item['content_html'] += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">No</td><td style="border:1px solid black;"></td>'
                        elif test_value == '1':
                            item['content_html'] += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">Yes</td><td style="border:1px solid black;"></td>'
                        else:
                            item['content_html'] += '<td style="white-space:nowrap; text-align:center; padding:0 8px 0 8px; border:1px solid black;">{}</td><td style="border:1px solid black;"></td>'.format(test_value.title())
                    item['content_html'] += '</tr>'
        item['content_html'] += '</table></div>'

    if page_data.get('features'):
        item['content_html'] += '<h2>Specs (official)</h2><table style="width:100%;">'
        for i, spec in enumerate(page_data['features']):
            if i % 2 == 0:
                item['content_html'] += '<tr style="line-height:2em; background-color:#ccc;">'
            else:
                item['content_html'] += '<tr style="line-height:2em;">'
            item['content_html'] += '<td style="white-space:nowrap; padding-right:8px;">{}</td>'.format(spec['name'])
            vals = []
            for val in spec['values']:
                if isinstance(val['text'], str):
                    if val.get('url'):
                        vals.append('<a href="{}">{}</a>'.format(val['url'], val['text']))
                    else:
                        vals.append(val['text'])
                elif isinstance(val['text'], list):
                    for v in val['text']:
                        if v.get('url'):
                            vals.append('<a href="{}">{}</a>'.format(v['url'], v['text']))
                        else:
                            vals.append(v['text'])
            item['content_html'] += '<td style="padding-left:8px;">{}</td></tr>'.format(' | '.join(vals))
        item['content_html'] += '</table>'

    item['content_html'] += add_comparison([item['id']])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/catalog/' not in url:
        logger.warning('unhandled feed url ' + url)
        return None
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = 'https://api.runrepeat.com/api/category/page/' + paths[-1]
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    page_data = api_json['page_data']

    if page_data['filter'].get('selectedOptions'):
        filters = '&filter%5B%5D=' + '&filter%5B%5D='.join(map(str, page_data['filter']['selectedOptions']))
    else:
        filters = ''
    api_url = 'https://api.runrepeat.com/get-documents?from=0&size=10{}&f_id={}&c_id={}&orderBy=newest&page_gender=false&event=%7B%22type%22:%22sort%22,%22value%22:%22newest%22%7D'.format(filters, page_data['filter']['id'], page_data['category']['id'])
    print(api_url)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for product in api_json['products']:
        product_url = 'https://runrepeat.com/' + product['slug']
        if save_debug:
            logger.debug('getting content for ' + product_url)
        item = get_content(product_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = page_data['page']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
