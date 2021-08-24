import json, re
from bs4 import BeautifulSoup
from datetime import datetime

import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  soup = BeautifulSoup(article_html, 'html.parser')
  next_data = soup.find('script', id='__NEXT_DATA__')
  if not next_data:
    return None

  next_json = json.loads(next_data.string)
  if save_debug:
    utils.write_file(next_json, './debug/debug.json')

  apollo_state = next_json['props']['apolloState']

  page_json = next_json['props']['pageProps']['page']
  if next_json['props']['pageProps'].get('video'):
    page_json = next_json['props']['pageProps']['video']

  item = {}
  item['id'] = page_json['id']
  item['url'] = url
  item['title'] = page_json['title']

  date = page_json['publishDate']
  if date.endswith('Z'):
    date = date.replace('Z', '+00:00')
  elif date.endswith('+0000'):
    date = date.replace('+0000', '+00:00')
  dt = datetime.fromisoformat(date)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  if page_json.get('modifiedDate'):
    date = page_json['modifiedDate']
    if date.endswith('Z'):
      date = date.replace('Z', '+00:00')
    elif date.endswith('+0000'):
      date = date.replace('+0000', '+00:00')
    dt = datetime.fromisoformat(date)
    item['date_modified'] = dt.isoformat()

  # Check age
  if 'age' in args:
    if not utils.check_age(item, args):
      return None

  if page_json.get('authorSocialDetails'):
    authors = []
    for author in page_json['authorSocialDetails']:
      authors.append(author['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  if page_json.get('tags'):
    item['tags'] = []
    for tag in page_json['tags']:
      if isinstance(tag, str):
        item['tags'].append(tag)
      elif isinstance(tag, dict):
        item['tags'].append(tag['displayName'])
  if page_json.get('categories'):
    if not item.get('tags'):
      item['tags'] = []
    for tag in page_json['categories']:
      if isinstance(tag, str):
        item['tags'].append(tag)
      elif isinstance(tag, dict):
        item['tags'].append(tag['displayName'])

  item['_image'] = page_json['thumbnailUrl'] + '?width=1000'

  if page_json['__typename'] == 'Video':
    item['summary'] = page_json['description']
    video = utils.closest_dict(page_json['assets'], 'width', 640)
    poster = page_json['thumbnailUrl'] + '?width=1000'
    item['content_html'] = utils.add_video(video['url'], 'video/mp4', poster)
    item['content_html'] += '<p>{}</p>'.format(page_json['description'])

  else:
    if page_json.get('review'):
      item['summary'] = page_json['review']['verdict']
    else:
      item['summary'] = page_json['promoSummary']

    page_html = ''
    for html in page_json['paginatedHtmlPage']:
      page_html += html

    page_soup = BeautifulSoup(page_html, 'html.parser')
    for el in page_soup.find_all('section'):
      if el.get('data-transform'):
        if re.search(r'commerce-deal|mobile-ad-break|object-feedback|poll', el['data-transform']):
          el.decompose()

        elif el['data-transform'] == 'image-with-caption':
          el_html = utils.add_image(el['data-image-url'], el['data-image-title'])
          el.insert_after(BeautifulSoup(el_html, 'html.parser'))
          el.decompose()

        elif el['data-transform'] == 'slideshow':
          for key, val in apollo_state['ROOT_QUERY'].items():
            if key.startswith('slideshow') and re.search(r'\"{}\"'.format(el['data-value']), key):
              el_html = '<h2 class="slideshow">Gallery</h2>'
              n = len(val['slideshowImages:{}']['images'])
              for i, image in enumerate(val['slideshowImages:{}']['images']):
                img_src = apollo_state[image['__ref']]['url']
                caption = '[{}/{}] '.format(i+1, n)
                if apollo_state[image['__ref']].get('caption'):
                  caption += apollo_state[image['__ref']]['caption']
                el_html += utils.add_image(img_src + '?width=1000', caption)
              # Append slideshows to end
              page_soup.append(BeautifulSoup(el_html, 'html.parser'))
              el.decompose()
              break

        elif el['data-transform'] == 'ignvideo':
          for key, val in apollo_state['ROOT_QUERY'].items():
            if key.startswith('videoPlayerProps') and el['data-slug'] in key:
              video_json = apollo_state[val['__ref']]
              video = utils.closest_dict(video_json['assets'], 'width', 640)
              poster = video_json['thumbnails'][0]['url'] + '?width=1000'
              caption = video_json['metadata']['title']
              el_html = utils.add_video(video['url'], 'video/mp4', poster, caption)
              el.insert_after(BeautifulSoup(el_html, 'html.parser'))
              el.decompose()
              break

        elif el['data-transform'] == 'quoteBox':
          el_html = utils.add_pullquote(el.get_text())
          el.insert_after(BeautifulSoup(el_html, 'html.parser'))
          el.decompose()

        elif el['data-transform'] == 'divider':
          el.insert_after(BeautifulSoup('<hr width="80%" />', 'html.parser'))
          el.decompose()

        else:
          logger.warning('unhandled section data-transform={} in {}'.format(el['data-transform'], url))
    
    for el in page_soup.find_all('a'):
      if re.search(r'\.(gif|jpg|jpeg|png)$', el['href'], flags=re.I):
        el.insert_after(BeautifulSoup(utils.add_image(el['href'] + '?width=1000'), 'html.parser'))
        el.decompose()

    item['content_html'] = ''
    lead = False
    if page_json.get('headerImageUrl'):
      item['content_html'] += utils.add_image(page_json['headerImageUrl'] + '?width=1000')
      lead = True
    elif page_json.get('canWatchRead') and page_json['canWatchRead'] == True and page_json.get('relatedMediaId'):
      video_json = utils.get_url_json('https://mollusk.apis.ign.com/graphql?operationName=VideoPlayerProps&variables=%7B%22videoId%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22ef401f728f7976541dd0c9bd7e337fbec8c3cb4fec5fa64e3d733d838d608e34%22%7D%7D'.format(page_json['relatedMediaId']))
      if video_json:
        video = utils.closest_dict(video_json['data']['videoPlayerProps']['assets'], 'width', 640)
        poster = video_json['data']['videoPlayerProps']['thumbnails'][0]['url'] + '?width=1000'
        caption = video_json['data']['videoPlayerProps']['metadata']['title']
        item['content_html'] += utils.add_video(video['url'], 'video/mp4', poster, caption)
        lead = True
      else:
        for m in re.findall(r'"videoId":"([a-f0-9]+)","thumbnailUrl":"([^"]+)","url":"([^"]+)"', article_html):
          print(m[0])
          if m[0] == page_json['relatedMediaId']:
            video_url = 'https://www.ign.com/' + m[2]
            logger.debug('checking video content from ' + video_url)
            video_content = get_content(video_url, args, False)
            if video_content:
              video_soup = BeautifulSoup(video_content['content_html'], 'html.parser')
              video = video_soup.find('table')
              item['content_html'] += str(video)
              lead = True
            break
    if not lead:
      item['content_html'] += utils.add_image(item['_image'])

    verdict = ''
    is_review = False
    if page_json.get('review'):
      for key, value in page_json['review'].items():
        if key != '__typename' and value:
          is_review = True
          break

    if is_review:
      if page_json['review']['editorsChoice'] == True:
        editors_choice = '<span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span><br />'
      else:
        editors_choice = ''
      item['content_html'] += '<br/><div style="width:75%; padding:10px 10px 0 10px; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px;"><center>{}<h1 style="margin:0;">{}</h1>{}</center></p><p><i>{}</i></p><p><small>'.format(editors_choice, page_json['review']['score'], page_json['review']['scoreText'].upper(), page_json['review']['scoreSummary'])

      if page_json['object'].get('objectRegions') and page_json['object']['objectRegions'][0].get('ageRating'):
        if page_json['object']['objectRegions'][0].get('ageRatingDescriptors'):
          desc = []
          for it in page_json['object']['objectRegions'][0]['ageRatingDescriptors']:
            desc.append(it['name'])
          if len(desc) > 0:
            rating_desc = ' ({})'.format(', '.join(desc))
          else:
            rating_desc = ''
          item['content_html'] += '<br />Rating: {}{}'.format(page_json['object']['objectRegions'][0]['ageRating']['name'], rating_desc)

      if page_json['object'].get('genres'):
        genres = []
        for it in page_json['object']['genres']:
          genres.append(it['name'])
        item['content_html'] += '<br />Genre: {}'.format(', '.join(genres))
    
      if page_json['object'].get('objectRegions') and page_json['object']['objectRegions'][0].get('releases'):
        platforms = []
        for it in page_json['object']['objectRegions'][0]['releases']:
          if it.get('platformAttributes'):
            platforms.append(it['platformAttributes'][0]['name'])
        if len(platforms) > 0:
          item['content_html'] += '<br />Platforms: {}'.format(', '.join(platforms))

      if page_json['object'].get('producers'):
        producers = []
        for it in page_json['object']['producers']:
          producers.append(it['name'])
        item['content_html'] += '<br />Developers: {}'.format(', '.join(producers))
    
      if page_json['object'].get('publishers'):
        publishers = []
        for it in page_json['object']['publishers']:
          publishers.append(it['name'])
        item['content_html'] += '<br />Publishers: {}'.format(', '.join(publishers))

      if page_json['object'].get('objectRegions') and page_json['object']['objectRegions'][0]['releases'][0].get('timeframeYear'):
        item['content_html'] += '<br />Release date: {}'.format(page_json['object']['objectRegions'][0]['releases'][0]['timeframeYear'])
      elif page_json['object'].get('objectRegions') and page_json['object']['objectRegions'][0]['releases'][0].get('date'):
        date = page_json['object']['objectRegions'][0]['releases'][0]['date']
        if date.endswith('Z'):
          dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
          date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        item['content_html'] += '<br />Release date: {}'.format(date)
    
      item['content_html'] += '</small></p></div>'
      verdict = '<h2>Verdict</h2><p>{}</p>'.format(page_json['review']['verdict'])

    if verdict:
      el = page_soup.find(class_='slideshow')
      if el:
        el.insert_before(BeautifulSoup(verdict, 'html.parser'))
      else:
        page_soup.append(BeautifulSoup(verdict, 'html.parser'))
    item['content_html'] += str(page_soup)

  return item

def get_feed(args, save_debug=False):
  page_html = utils.get_url_html(args['url'])
  if not page_html:
    return None
  if save_debug:
    utils.write_file(page_html, './debug/debug.html')

  n = 0
  items = []
  feed = utils.init_jsonfeed(args)

  soup = BeautifulSoup(page_html, 'html.parser')

  for content_feed in soup.find_all(class_='content-feed-grid-wrapper'):    
    for a in content_feed.find_all('a', class_="item-body"):
      url = a['href']
      if not url.startswith('https://www.ign.com/'):
        url = 'https://www.ign.com' + a['href']
      if save_debug:
        logger.debug('getting content from ' + url)
      item = get_content(url, args, save_debug)
      if item:
        if utils.filter_item(item, args) == True:
          items.append(item)
          n += 1
          if 'max' in args:
            if n == int(args['max']):
              break
  feed['items'] = items.copy()
  return feed
  