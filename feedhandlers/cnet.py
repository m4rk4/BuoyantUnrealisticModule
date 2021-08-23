import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def get_leads_tracker_link(a_tag):
  dest_url = ''
  if a_tag.has_attr('data-component') and a_tag['data-component'] == 'leadsTracker':
    if a_tag.get('data-leads-tracker-options'):
      leads_json = json.loads(a_tag['data-leads-tracker-options'])
      if leads_json['trackingData'].get('_destCat'):
        dest_url = leads_json['trackingData']['_destCat']
      else:
        dest_url = utils.clean_referral_link(leads_json['trackingData']['destUrl'])
  return dest_url

def get_video_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(article_html)

  soup = BeautifulSoup(article_html, 'html.parser')
  video_player = soup.find(class_='videoPlayer')
  if video_player and video_player.get('data-video-player-options'):
    video_data = json.loads(video_player['data-video-player-options'])
    # Assume it's the first video in the playlist
    video_info = video_data['playlist'][0]
  else:
    logger.warning('unable to load video player data in ' + url)
    return None

  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(video_info, file, indent=4)

  item = {}
  item['id'] = video_info['id']
  item['url'] = url
  item['title'] = video_info['title']
  dt = datetime.strptime(video_info['datePublished'], '%Y-%m-%d %H:%M:%S')
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  item['author'] = {}
  item['author']['name'] = '{} {}'.format(video_info['author']['firstName'], video_info['author']['lastName'])
  item['_image'] = video_info['thumbnail']
  item['_video'] = video_info['mp4']
  item['summary'] = video_info['description']

  item['content_html'] = utils.add_video(video_info['mp4'], 'video/mp4', video_info['thumbnail'])

  for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
    ld_json = json.loads(el.string)
    if ld_json.get('@type') and ld_json['@type'] == 'VideoObject':
      if ld_json.get('transcript'):
        item['content_html'] += '<h4>Transcript:</h4><p>{}</p>'.format(ld_json['transcript'])
  return item

def get_content(url, args, save_debug=False):
  item = {}
  clean_url = utils.clean_url(url)

  if '/videos/' in clean_url:
    return get_video_content(clean_url, args, save_debug)

  # Try to use the amphtml url
  page_url = ''
  is_amp = False
  if '/google-amp/' in clean_url:
    page_url = clean_url
    is_amp = True
  else:
    article_html = utils.get_url_html(clean_url)
    if not article_html:
      return None
    if save_debug:
      with open('./debug/debug.html', 'w', encoding='utf-8') as f:
        f.write(article_html)
    soup = BeautifulSoup(article_html, 'html.parser')
    amp_link = soup.find('link', rel='amphtml')
    if amp_link:
      page_url = amp_link['href']
      is_amp = True
    else:
      logger.warning('unable to find amphtml link in ' + clean_url)
      page_url = clean_url

  page_html = utils.get_url_html(page_url)
  if not page_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(page_html)

  soup = BeautifulSoup(page_html, 'html.parser')

  el = soup.find('script', attrs={"type": "application/ld+json"})
  ld_json = json.loads(el.string)
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(ld_json, file, indent=4)
  if ld_json.get('review'):
    ld_info = ld_json['review']
  else:
    ld_info = ld_json

  item['id'] = clean_url
  item['url'] = clean_url
  item['title'] = ld_info['headline']

  if ld_info['datePublished'].endswith('Z'):
    dt = datetime.fromisoformat(ld_info['datePublished'].replace('Z', '+00:00'))
  else:
    dt = datetime.strptime(ld_info['datePublished'], '%Y-%m-%dT%H:%M:%S%z').astimezone(timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  if ld_info['dateModified'].endswith('Z'):
    dt = datetime.fromisoformat(ld_info['dateModified'].replace('Z', '+00:00'))
  else:
    dt = datetime.strptime(ld_info['dateModified'], '%Y-%m-%dT%H:%M:%S%z').astimezone(timezone.utc)
  item['date_modified'] = dt.isoformat()

  item['author'] = {}
  item['author']['name'] = ld_info['author']['name']

  item['tags'] = []
  for el in soup.find_all(class_='tagList'):
    for it in el.find_all('a', class_='tag'):
      if not 'interestOnly' in it['class']:
        item['tags'].append(it.get_text())

  if ld_info.get('thumbnailUrl'):
    item['_image'] = ld_info['thumbnailUrl']
  elif ld_info.get('image'):
    item['_image'] = ld_info['image']['url']

  if ld_info.get('description'):
    item['summary'] = ld_info['description']
  else:
    el = soup.find('meta', attrs={"name":"description"})
    if el:
      item['summary'] = el['content']

  item['content_html'] = ''
  parsing = True
  while parsing:
    article = soup.find(class_=re.compile(r'article-main-body|editorialBody'))
    if not article:
      article = soup.find(id='editorReview')
    if not article:
      logger.warning('unable to find article body in ' + clean_url)
      break

    article.attrs.clear()
    for i in range(2):
      if article.contents[i].name and article.contents[i].name == 'div':
        if article.contents[i].has_attr('class') and 'row' in article.contents[i]['class']:
          article.contents[i].unwrap()

    editors_choice = ''

    # Remove these elements
    for el in article.find_all('amp-ad'):
      el.decompose()

    for el in article.find_all(class_=re.compile('ad-slot|amp-ad|injectedAd|m-linkstack|newsletter|related-links|relatedContent', flags=re.I)):
      el.decompose()

    for el in article.find_all(id='autoRelatedLinks'):
      el.decompose()

    # Remove "read more" links
    for el in article.find_all('strong'):
      if re.search(r'Read More', el.get_text(), flags=re.I):
        if el.parent.name == 'p':
          el.parent.decompose()

    for el in article.find_all('figure', class_=['image', 'img']):
      new_html = ''
      caption = ''
      if 'hasCaption' in el['class']:
        it = el.find(class_='caption')
        if it:
          caption += it.get_text()
        it = el.find(class_='credit')
        if it:
          if caption:
            caption += ' '
          caption += 'Credit: ' + it.get_text().strip()
      if is_amp:
        img = el.find('amp-img')
      else:
        img = el.find('img')
      if img:
        if img.get('src'):
          new_html = utils.add_image(img['src'], caption)
        elif img.get('data-original'):
          new_html = utils.add_image(img['data-original'], caption)
        else:
          logger.warning('unhandled img {} in {}'.format(str(img), url))
      else:
        # Gif's may be videos
        video = el.find('amp-video')
        if video:
          new_html = utils.add_video(video['src'], 'video/mp4', video.get('poster'), caption)
        else:
          logger.warning('unable to determine image src in ' + url)
      if new_html:
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in article.find_all(class_='gallery'):
      new_html = '<h2>Gallery: {}</h2>'.format(el.select('h2.hed')[0].get_text())
      for it in el.find_all('img'):
        new_html += utils.add_image(it['src'])
      link = el.select('a.allLink')[0].get('href')
      if not link.startswith('http'):
        link = 'https://www.cnet.com' + link
      it = el.find(class_='more')
      if it:
        more = it.get_text()
      else:
        more = 'See all photos'
      new_html += '<p><a href="{}">{}</a></p>'.format(link, more)
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

    for el in article.find_all(class_='video'):
      new_html = ''
      video_src = ''
      caption = ''
      poster = ''
      it = el.find(class_='videoText')
      if it:
        caption += it.get_text()
      it = el.find('amp-video')
      if it:
        video_src = it['src']
        poster = it.get('poster')
      else:
        # Try amp-video-iframe
        it = el.find('amp-video-iframe')
        if it:
          video_content = get_video_content(it['src'], None, save_debug)
          if video_content:
            video_src = video_content['_video']
            poster = video_content['_image']
        else:
          logger.warning('unable to determine video src in ' + url)
      if video_src:
        new_html = utils.add_video(video_src, 'video/mp4', poster, caption)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in article.find_all('amp-video-iframe'):
      video_content = get_video_content(el['src'], None, save_debug)
      if video_content:
        video_src = video_content['_video']
        poster = video_content['_image']
        new_html = utils.add_video(video_src, 'video/mp4', poster, caption)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in article.find_all(class_='op-social'):
      new_html = ''
      if el.find('amp-youtube'):
        new_html = utils.add_youtube(el.find('amp-youtube').get('data-videoid'))
      elif el.find('amp-twitter'):
        tweet_url = el.find('amp-twitter').get('data-tweetid')
        if tweet_url:
          tweet = utils.add_twitter(tweet_url)
          if tweet:
            new_html = tweet
          else:
            logger.warning('unable to add tweet {} in {}'.format(tweet_url, url))
      else:
        logger.warning('unhandled op-social content in ' + url)
      if new_html:
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()
      
    for el in article.find_all('aside', class_='pullQuote'):
      author = ''
      if el.div:
        author = el.div.get_text()
        el.div.decompose()
      new_html = utils.add_pullquote(el.get_text(), author)
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

    for el in article.find_all(class_=re.compile(r'\biframeWrap\b|\biframeSpacerWrap\b')):
      it = el.find('amp-iframe')
      if it and it.has_attr('src'):
        if re.search(r'megaphone\.fm', it['src']):
          # Typically a podcast
          el.decompose()
        else:
          text = el.get_text().strip()
          if not text:
            text = it['src']
          new_html = '<p>Embedded iframe: <a href="{}">{}</a></p>'.format(it['src'], text)
          el.insert_after(BeautifulSoup(new_html, 'html.parser'))
          el.decompose()
      else:
        logger.warning('unhandled iframe in ' + url)

    for el in article.find_all('div', class_='c-priceCard'):
      new_html = ''
      lead = el.find('figure')
      it = el.find(class_='c-priceBox_chunk')
      if it:
        head = it.find(class_='c-priceBox_head').get_text().strip()
        price = it.find(class_='c-priceBox_price').get_text().strip()
        new_html += '<center><strong><small>{}</small>: {}</strong></center>'.format(head, price)
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      if lead:
        el.insert_after(lead)
      else:
        logger.warning('no lead image or video in priceCard found in ' + url)
      el.decompose()

    for el in article.find_all('div', class_=re.compile(r'\bc-reviewCard\b|\bc-reviewPostcap\b')):
      it = article.find(class_=re.compile('editorsChoiceBadge'))
      if it or editors_choice:
        editors_choice = '<span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span><br />'
        if it:
          it.decompose()
      it = el.find('img')
      if it:
        img_src = it['src']
      else:
        img_src = ''
      it = el.find(class_='c-metaCard_rating')
      if it:
        rating = it.get_text().strip()
      else:
        rating = 'N/A'
      new_html = '<div style="width:75%; padding:10px 10px 0 10px; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px;"><center>{}<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><defs><mask id="hole"><rect width="100%" height="100%" fill="white"/><circle r="20%" cx="50%" cy="100%" fill="black"/></mask></defs><image width="100%" height="100%" xlink:href="{}" mask="url(#hole)"></image><text x="50%" y="100%" text-anchor="middle" font-size="2em" font-weight="bold" font-family="sans-serif">{}</text></svg>'.format(editors_choice, img_src, rating)
      it = el.find(class_='c-metaCard_prodName')
      if it:
        new_html += '<h3>{}</h3>'.format(it.get_text())
      it = el.find(class_='c-priceBox_chunk')
      if it:
        head = it.find(class_='c-priceBox_head').get_text()
        price = it.find(class_='c-priceBox_price').get_text()
        new_html += '<p><small>{}</small><br />{}</p>'.format(head, price)
      if el.find('a', class_='button'):
        for i, a in enumerate(el.find_all('a', class_='button')):
          if a.get('data-leads-tracker-options'):
            leads_json = json.loads(a['data-leads-tracker-options'])
            if leads_json['trackingData'].get('_destCat'):
              dest_url = leads_json['trackingData']['_destCat']
            else:
              dest_url = utils.clean_referral_link(leads_json['trackingData']['destUrl'])
            if i == 0:
              new_html += '<p>'
            else:
              new_html += '<br />'
            new_html += '<a href="{}">{}</a>'.format(dest_url, leads_json['trackingData']['text'])
        new_html += '</p>'
      new_html += '</center>'

      for it in el.find_all('div', class_='c-reviewCard_chunk'):
        new_html += '<h3>{}</h3><ul>'.format(it.find(class_='c-reviewCard_head').get_text())
        if it.find(class_='c-reviewCard_listText'):
          for li in it.find_all(class_='c-reviewCard_listText'):
            new_html += '<li>{}</li>'.format(li.get_text())
        elif it.find(class_='c-reviewCard_compProd'):
          names = []
          for li in it.find_all('a', class_='c-reviewCard_name'):
            name = {}
            name['text'] = li.get_text()
            name['url'] = li['href']
            names.append(name)
          ratings = []
          for li in it.find_all('a', class_='c-reviewCard_rating'):
            rating = {}
            rating['text'] = li.get_text()
            rating['url'] = li['href']
            ratings.append(rating)
          prices = []
          for li in it.find_all('a', class_='c-reviewCard_priceLink'):
            price = {}
            price['text'] = li.get_text().strip()
            price['url'] = get_leads_tracker_link(li)
            prices.append(price)
          for i in range(len(names)):
            new_html += '<li><a href="{}">{}</a> &ndash; <a href="{}">{}</a> (<a href="{}">{}</a>)</li>'.format(ratings[i]['url'], ratings[i]['text'], names[i]['url'], names[i]['text'], prices[i]['url'], prices[i]['text'])
        new_html += '</ul>'

      # Test score breakdown
      for it in el.find_all(class_='c-reviewPostcap_breakdown'):
        title = it.find('h3').get_text()
        labels = []
        for val in it.find_all(class_='c-reviewPostcap_rateTitle'):
          labels.append(val.get_text())
        values = []
        for val in it.find_all(class_='c-reviewPostcap_rating'):
          values.append(float(val.get_text()))
        new_html += utils.add_barchart(labels, values, title, max_value=10, percent=False, border=False, width="100%")
    
      # Specs
      for it in el.find_all(class_='c-reviewPostcap_specs'):
        title = it.find('h3').get_text()
        labels = []
        values = []
        for val in it.find_all('span'):
          if val.has_attr('class') and 'c-reviewPostcap_val' in val['class']:
            values.append(val.get_text().strip())
          else:
            labels.append(val.get_text().strip())
        if len(labels) != len(values):
          logger.warning('error parsing c-reviewPostcap_specs in ' + url)
        else:
          new_html += '<div style="width:100%; padding-left:10px; padding-right:10px; padding-top:0px; padding-bottom:10px; margin-left:auto; margin-right:auto;"><h3>{}</h3><table width="100%"><tr>'.format(title)
          for i in range(len(values)):
            new_html += '<tr><td>{}</td><td>{}</td>'.format(labels[i], values[i])
          new_html += '</table></tr></div>'

      new_html += '</div>'
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

      for el in article.find_all(class_='type_perfchart'):
        new_html = ''
        if el.h2:
          new_html += '<h2>{}</h2>'.format(el.h2.get_text())
        labels = []
        for it in el.find_all(class_='name'):
          labels.append(it.get_text())
        values = []
        for it in el.find_all(class_='rating'):
          val = it.get_text().replace(',', '')
          values.append(int(val))
        caption = ''
        if el.figcaption:
          caption = el.figcaption.get_text()
        new_html += utils.add_barchart(labels, values, caption=caption, percent=False)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    # Fix links (do this after the review card)
    for el in article.find_all('a'):
      # cnet.com links
      if el.get('href') and el['href'].startswith('/'):
        href = el['href']
        el['href'] = 'https://www.cnet.com' + href

      # Referral links
      if el.has_attr('data-component') and el['data-component'] == 'leadsTracker':
        if el.get('data-leads-tracker-options'):
          leads_json = json.loads(el['data-leads-tracker-options'])
          if leads_json['trackingData'].get('_destCat'):
            dest_url = leads_json['trackingData']['_destCat']
          else:
            dest_url = utils.clean_referral_link(leads_json['trackingData']['destUrl'])
        else:
          dest_url = el['href']
        el['href'] = dest_url

      if el.get('href'):
        href = el['href']
        el.attrs.clear()
        el['href'] = href

    for el in article.find_all(class_='listicle'):
      it = el.find('h2')
      new_html = '<h2>{}</h2>'.format(it.string)
      it = el.find(class_='subhedlisticle')
      if it and it.h3:
        new_html += '<h3><a href="{}">{}</a></h3>'.format(it.a['href'], it.h3.get_text())
      it = article.find(class_=re.compile('editorsChoiceBadge'))
      if it:
        new_html += '<span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span><br />'
        it.decompose()
      if el.find(class_='itemImage'):
        caption = ''
        if el.find(class_='imageCredit'):
          caption += el.find(class_='imageCredit').get_text()
        img = el.select('.itemImage amp-img')
        new_html += utils.add_image(img[0]['src'], caption)
      for it in el.find_all('p'):
        if not (len(it.contents) == 1 and it.contents[0] == '\xa0'):
          new_html += str(it)
      if el.find(class_='buttonWrap'):
        new_html += '<ul>'
        for it in el.select('.buttonWrap .leadButton'):
          new_html += '<li><a href="{}">{}</a></li>'.format(it.a['href'], it.get_text())
        new_html += '</ul>'
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

    for el in article.find_all(class_='pipe'):
      el.insert_after(BeautifulSoup('&nbsp;|&nbsp;', 'html.parser'))
      el.decompose()

    for el in article.find_all(class_=re.compile('chartWrapper|comLink|inline-review-hero|link|type_geekboxchart')):
      if ('link' in el['class'] or 'comLink' in el['class']) and el.name != 'span':
          continue
      el.unwrap()

    for el in article.find_all(class_='cnetbuybutton'):
      el.decompose()

    # Clean up or alert to unhandled elements
    for el in article.find_all(class_=True):
      if el.name == 'time':
        continue
      r = re.compile(r'c-endLinks|speakableTextP\d')
      if any(r.match(c) for c in el['class']):
        el.attrs.clear()
      else:
        logger.warning('unhandled class {} in {}'.format(el['class'], url))

    # Check for lead image
    el = soup.find(id='article-hero')
    if el:
      caption = ''
      it = el.find(class_='hero-credit')
      if it:
        caption += it.get_text()
      img = el.find('amp-img')
      item['content_html'] += utils.add_image(img['src'], caption)

    item['content_html'] += str(article)

    el = soup.find('a', rel='next')
    if el:
      if el['href'].startswith('/'):
        next_page = 'https://www.cnet.com' + el['href']
      else:
        next_page = el['href']
      article_html = utils.get_url_html(next_page)
      if article_html:
        soup = BeautifulSoup(article_html, 'html.parser')
    else:
      parsing = False

  return item

def get_feed(args, save_debug=False):
  n = 0
  items = []
  feed = rss.get_feed(args, save_debug)
  for feed_item in feed['items']:
    if save_debug:
      logger.debug('getting content for ' + feed_item['url'])
    item = get_content(feed_item['url'], args, save_debug)
    if utils.filter_item(item, args) == True:
      items.append(item)
      n += 1
      if 'max' in args:
        if n == int(args['max']):
          break
  feed['items'] = items.copy()
  return feed