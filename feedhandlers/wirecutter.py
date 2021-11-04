import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def resize_image(src, width=1024):
  if not src.startswith('https'):
    if not src.startswith('wp-content'):
      img_src = 'https://cdn.thewirecutter.com/wp-content/uploads/' + src
    else:
      img_src = 'https://cdn.thewirecutter.com/' + src
  else:
    img_src = src
  split_url = urlsplit(img_src)
  return '{}://{}{}?auto=webp&width={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)

def get_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None

  soup = BeautifulSoup(article_html, 'html.parser')
  next_data = soup.find('script', id='__NEXT_DATA__')
  if not next_data:
    return None

  next_json = json.loads(next_data.string)
  if save_debug:
    utils.write_file(next_json, './debug/debug.json')

  post_json = next_json['props']['pageProps']['post']

  item = {}
  item['id'] = post_json['guid']
  item['url'] = url
  if post_json.get('metaTitle'):
    item['title'] = post_json['metaTitle']
  else:
    item['title'] = post_json['title']

  dt = datetime.fromisoformat(post_json['modifiedDateISO']).astimezone(timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  authors = []
  for author in post_json['authors']:
    authors.append(author['displayName'])
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  tags = []
  if post_json.get('primaryTerms'):
    for tag in post_json['primaryTerms']:
      tags.append(tag)
  if post_json.get('auxiliaryTerms'):
    for tag in post_json['auxiliaryTerms']:
      tags.append(tag)
  if tags:
    item['tags'] = tags.copy()

  item['_image'] = resize_image(post_json['heroImage']['source'])
  item['summary'] = post_json['metaDescription']

  def format_section(section):
    end_tag = ''
    section_html = ''
    if section['type'] == 'tag':
      if re.search(r'^(b|i|em|h\d|li|ol|p|ul|span|strong|sub|sup|tbody|td|tr)$', section['name']):
        section_html += '<{}>'.format(section['name'])
        end_tag = '</{}>'.format(section['name'])

      elif section['name'] == 'a':
        href = section['attribs']['href']
        #if section['attribs'].get('class') and section['attribs']['class'] == 'product-link':
        #  href = utils.get_redirect_url(href)
        section_html += '<a href="{}">'.format(href)
        end_tag = '</a>'

      elif section['name'] == 'br':
        section_html += '<br/>'

      elif section['name'] == 'img':
        section_html += utils.add_image(resize_image(section['attribs']['src']))

      elif section['name'] == 'source':
        if section['attribs']['type'] == 'video/mp4':
          if '.gif' in section['attribs']['src']:
            m = re.search(r'^(.*\.gif)\?', section['attribs']['src'])
            section_html += utils.add_image(m.group(1))
          else:
            section_html += utils.add_video(section['attribs']['src'], 'video/mp4')
        else:
          logger.warning('unhandled source type {}'.format(section['attribs']['type']))

      elif section['name'] == 'table':
        section_html += '<table style="border: 1px solid black">'
        end_tag = '</table><br/>'

      elif section['name'] == 'shortcode-callout':
        section_html += '<div style="width:75%; padding:10px 10px 0 10px; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px;">'
        for callout in section['dbData']['callouts']:
          section_html += '<h3 style="margin-top:0; margin-bottom:0;">{}:<br/><em>{}</em></h3><h4 style="margin-top:0; margin-bottom:0;">{}</h4><img width="100%" src="{}"/><p>{}</p>'.format(callout['ribbon'], callout['name'], callout['title'], callout['images']['full'], callout['description'])
          if callout.get('sources'):
            section_html += '<ul>'
            for source in callout['sources']:
              if source.get('rawUrl'):
                section_html += '<li><a href="{}">{} from {}</a></li>'.format(source['rawUrl'], source['price']['formatted'], source['store'])
            section_html += '</ul>'
        section_html += '</div>'

      elif section['name'] == 'shortcode-caption':
        figure = ''
        for child in section['children']:
          figure += format_section(child)
        m = re.search(r'<img src="([^"]+)"', figure)
        img_src = m.group(1)
        m = re.search(r'<a href="([^"]+)"><img', figure)
        if m:
          img_link = m.group(1)
        else:
          img_link = ''
        captions = []
        caption = re.sub(r'<figure>.*<\/figure>', '', figure).strip()
        if caption:
          captions.append(caption)
        if section['dbData'].get('credit'):
          captions.append(section['dbData']['credit'])
        section_html += utils.add_image(img_src, ' | '.join(captions), link=img_link)

      elif section['name'] == 'shortcode-gallery':
        for image in section['dbData']:
          captions = []
          if image.get('excerpt'):
            captions.append(image['excerpt'])
          if image.get('credit'):
            captions.append(image['credit'])
          img_src = ''
          if image.get('dbData'):
            img_src = image['dbData'].get('full')
          if not img_src:
            img_src = image['imagePaths'].get('full')
            if not img_src:
              img_src = image['imagePaths'].get('file')
          section_html += utils.add_image(resize_image(img_src), ' | '.join(captions))

      elif section['name'] == 'shortcode-pullquote':
        section_html += utils.open_pullquote()
        end_tag += utils.close_pullquote()

      elif re.search(r'^(shortcode\-recirc|video)$', section['name']):
        # recirc is usually related articles
        pass

      else:
        logger.debug('unhandled tag {}'.format(section['name']))

    elif section['type'] == 'text':
      section_html += section['data']

    else:
      logger.debug('unhandled section type {}'.format(section['type']))

    if section.get('children') and section['name'] != 'shortcode-caption':
      for child in section['children']:
        section_html += format_section(child)

    section_html += end_tag
    return section_html

  item['content_html'] = utils.add_image(resize_image(post_json['heroImage']['source']), post_json['heroImage']['caption'])

  if post_json.get('structuredLede'):
    for section in post_json['structuredLede']:
      item['content_html'] += format_section(section)
    item['content_html'] += '<hr/>'

  if post_json.get('structuredIntro'):
    for section in post_json['structuredIntro']:
      item['content_html'] += format_section(section)

  if post_json.get('structuredContent'):
    for section in post_json['structuredContent']:
      item['content_html'] += format_section(section)

  if post_json.get('chapters'):
    for chapter in post_json['chapters']:
      item['content_html'] += '<hr/><h3>{}</h3>'.format(chapter['title'])
      for section in chapter['body']:
        item['content_html'] += format_section(section)

  if post_json.get('listSections'):
    for list in post_json['listSections']:
      if list.get('title'):
        item['content_html'] += '<h3><u>{}</u></h3>'.format(list['title'])
      for product_item in list['productItems']:
        if product_item.get('title'):
          item['content_html'] += '<h3>{}</h3>'.format(product_item['title'])
        if product_item.get('body'):
          body = json.loads(product_item['body'])
          for section in body:
            item['content_html'] += format_section(section)
        for product in product_item['products']:
          item['content_html'] += '<div><img style="float:left; margin-right:8px; width:128px;" src="{}"/><div style="overflow:auto; display:block;"><b>{}</b><br/><a href="https://www.nytimes.com/wirecutter{}">{}</a><br/><small>&bull;&nbsp;<a href="{}">${:0.2f} at {}</a></small></div><div style="clear:left;"></div><br/>'.format(product['relatedProductData']['productImageUrl'], product['relatedProductData']['productName'], product['relatedPostLink'], product['title'], product['relatedProductData']['sources'][0]['affiliateLink'], int(product['relatedProductData']['sources'][0]['sourcePrice'])/100, product['relatedProductData']['sources'][0]['merchantName'])

  return item