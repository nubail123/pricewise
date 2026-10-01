import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight, ArrowUpRight, ArrowDown, Heart, Search, X, Check, Sparkles,
  SlidersHorizontal, ChevronDown, ShieldCheck, Clock3, Smartphone, Laptop,
  Headphones, House, Gamepad2, ShoppingBag, Star, RefreshCw, LayoutGrid,
  List, AlertCircle, ExternalLink, CheckCircle2, Database, Copy, Info,
  PackageSearch, Download, Bookmark, Menu, Leaf, CircleHelp,
} from 'lucide-react';

import RETAILERS from '../retailers.json';

const STORES = RETAILERS.map(store => store.id);
const STORE_MAP = Object.fromEntries(RETAILERS.map(store => [store.id, store]));
const storeMeta = store => STORE_MAP[store] || { name: store, shortName: store, logo: store, color: '#435943' };
const storeName = store => storeMeta(store).name;
function offerEntries(product) { return Object.entries(product.offers).filter(([store, offer]) => STORES.includes(store) && offer).sort((a, b) => (a[1].available === true ? 0 : a[1].available === false ? 2 : 1) - (b[1].available === true ? 0 : b[1].available === false ? 2 : 1) || a[1].price - b[1].price); }

const SUGGESTIONS = ['AirPods Pro 3', 'iPhone 16', 'Sony WH-1000XM5', 'Samsung Galaxy Watch 8', 'Dyson V15', 'MacBook Air M3'];
const CATEGORIES = [
  { label: 'All categories', icon: LayoutGrid, query: null },
  { label: 'Mobiles', icon: Smartphone, query: 'smartphones' },
  { label: 'Audio', icon: Headphones, query: 'wireless headphones' },
  { label: 'Computing', icon: Laptop, query: 'laptops' },
  { label: 'Home & living', icon: House, query: 'air fryer' },
  { label: 'Gaming', icon: Gamepad2, query: 'PlayStation 5' },
  { label: 'Beauty', icon: Sparkles, query: 'skincare' },
];

function readStorage(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return Array.isArray(value) ? value : fallback;
  } catch { return fallback; }
}
function writeStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
}
function priceValue(product, preferredStore = 'all') {
  if (STORES.includes(preferredStore) && product.offers[preferredStore]) return product.offers[preferredStore].price;
  const offers = offerEntries(product).map(([, offer]) => offer);
  const available = offers.filter(offer => offer.available === true);
  const unknown = offers.filter(offer => offer.available !== false);
  return Math.min(...(available.length ? available : unknown.length ? unknown : offers).map(offer => offer.price));
}
function normalizeSavedProduct(item) {
  const offers = Object.fromEntries(STORES.map(store => [store, item.offers?.[store] || null]));
  const entries = Object.entries(offers).filter(([, offer]) => offer && typeof offer.price === 'number' && Number.isFinite(offer.price) && offer.price > 0);
  const eligible = entries.filter(([, offer]) => offer.available === true);
  const min = eligible.length ? Math.min(...eligible.map(([, offer]) => offer.price)) : null;
  const max = eligible.length ? Math.max(...eligible.map(([, offer]) => offer.price)) : null;
  const difference = eligible.length >= 2 ? Number((max - min).toFixed(2)) : null;
  const lowestStores = eligible.length >= 2 ? eligible.filter(([, offer]) => offer.price === min).map(([store]) => store) : [];
  return {
    ...item,
    offers,
    offerCount: entries.length,
    availableOfferCount: eligible.length,
    priceDifference: difference,
    lowerStore: difference && lowestStores.length ? lowestStores[0] : null,
    lowestStores,
    match: entries.length > 1 ? (item.match || { level: 'likely', score: 0.9, reason: 'Saved comparison snapshot.' }) : { level: 'single', score: 0, reason: 'Saved single-store snapshot. Recheck to compare more stores.' },
  };
}
function savedSnapshots() {
  return readStorage('pricewise:saved', []).filter(item => item?.id && item?.title && STORES.some(store => item?.offers?.[store])).slice(0, 60).map(normalizeSavedProduct).filter(item => item.offerCount > 0);
}
function money(value) {
  return new Intl.NumberFormat('en-AE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}
function ago(iso) {
  if (!iso) return 'not checked yet';
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
  return `${Math.floor(seconds / 86400)} day${seconds >= 172800 ? 's' : ''} ago`;
}
function fullDate(iso) {
  return iso ? new Date(iso).toLocaleString('en-AE', { dateStyle: 'medium', timeStyle: 'short' }) : 'Not checked yet';
}
function searchUrl(store, query) {
  return storeMeta(store).search?.replace('{query}', encodeURIComponent(query)) || storeMeta(store).home;
}
async function getJSON(url, signal) {
  const response = await fetch(url, { signal });
  let data;
  try { data = await response.json(); } catch { throw new Error('The price-search backend is not reachable. Keep the server terminal running and try again.'); }
  if (!response.ok) {
    if (response.status === 404 || data?.detail === 'Not Found') {
      throw new Error('The price-search API was not reached on this port. Run the backend alongside the frontend, or run npm run build then npm start.');
    }
    const detail = Array.isArray(data.detail) ? 'Please enter a product name between 2 and 120 characters.' : data.detail;
    throw new Error(detail || 'We could not complete this search. Please try again.');
  }
  return data;
}

function Logo({ small = false }) {
  return <span className={`wordmark ${small ? 'small' : ''}`}>
    <svg width="31" height="34" viewBox="0 0 34 38" fill="none" aria-hidden="true">
      <path d="M4 17.5a3 3 0 0 1 3-3h6v21H7a3 3 0 0 1-3-3v-15Z" fill="currentColor" />
      <path d="M21 5.5a3 3 0 0 1 3-3h6v21h-6a3 3 0 0 1-3-3v-15Z" fill="currentColor" />
      <path d="m5.5 31.5 21-21" stroke="#f18a60" strokeWidth="4.3" strokeLinecap="round" />
    </svg>
    pricewise<span className="logo-period">.</span>
  </span>;
}
function Flag() {
  return <svg className="uae-flag" width="22" height="15" viewBox="0 0 30 20" aria-label="United Arab Emirates">
    <rect width="30" height="20" rx="2" fill="white" />
    <path fill="#1d8d5b" d="M0 0h30v6.67H0z" /><path fill="#202523" d="M0 13.33h30V20H0z" /><path fill="#e5524c" d="M0 0h8v20H0z" />
  </svg>;
}
function StoreLogo({ store, large = false }) {
  return store === 'noon'
    ? <span className={`store-logo noon ${large ? 'large' : ''}`} title="Noon">noon<span className="noon-dot" /></span>
    : <span className={`store-logo ${store} ${large ? 'large' : ''} ${store === 'jumbo' ? '' : 'extra-store'}`} style={{ '--retailer-color': storeMeta(store).color }} title={storeName(store)} aria-label={storeName(store)}>{storeMeta(store).logo}</span>;
}
function ProductImage({ product, className = '' }) {
  const [stage, setStage] = useState(0);
  useEffect(() => setStage(0), [product.image]);
  const src = stage === 0 ? `/api/image?url=${encodeURIComponent(product.image)}` : product.image;
  return product.image && stage < 2
    ? <img className={`product-image ${className}`} src={src} alt={product.title} loading="lazy" referrerPolicy="no-referrer" onError={() => setStage(s => s + 1)} />
    : <div className={`image-placeholder ${className}`}><PackageSearch size={45} strokeWidth={1.2} /><span>Image unavailable</span></div>;
}
function Amount({ value, className = '' }) {
  return <span className={`amount ${className}`}><span className="currency">AED</span> {money(value)}</span>;
}

function SearchForm({ value, onChange, onSearch, loading, history, inputRef, error, compact = false }) {
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const formRef = useRef(null);
  const options = value.trim()
    ? SUGGESTIONS.filter(item => item.toLowerCase().includes(value.toLowerCase()) && item.toLowerCase() !== value.toLowerCase()).slice(0, 4)
    : [...new Set([...history, ...SUGGESTIONS])].slice(0, 5);
  useEffect(() => {
    const close = event => { if (!formRef.current?.contains(event.target)) setShowSuggestions(false); };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);
  function choose(query) { setShowSuggestions(false); onChange(query); onSearch(query); }
  return <div className={`search-block ${compact ? 'compact' : ''}`}>
    <form className={`search-form ${error ? 'input-error' : ''}`} ref={formRef} onSubmit={event => {
      event.preventDefault();
      setShowSuggestions(false);
      onSearch(highlight >= 0 && options[highlight] ? options[highlight] : value);
    }}>
      <Search size={22} strokeWidth={1.8} className="search-icon" />
      <input ref={inputRef} value={value} onChange={event => { onChange(event.target.value); setHighlight(-1); setShowSuggestions(true); }}
        onFocus={() => setShowSuggestions(true)} onKeyDown={event => {
          if (event.key === 'Escape') setShowSuggestions(false);
          if (event.key === 'ArrowDown' && options.length) { event.preventDefault(); setShowSuggestions(true); setHighlight(index => (index + 1) % options.length); }
          if (event.key === 'ArrowUp' && options.length) { event.preventDefault(); setHighlight(index => (index - 1 + options.length) % options.length); }
        }} placeholder="What’s on your wishlist?" aria-label="Search for a product" maxLength={120} autoComplete="off" enterKeyHint="search" />
      {value && <button type="button" className="clear-search icon-button" aria-label="Clear search" onClick={() => { onChange(''); inputRef.current?.focus(); }}><X size={17} /></button>}
      <button type="submit" className="search-submit" disabled={loading}>{loading ? <RefreshCw size={18} className="spin" /> : <><span>Compare<span className="desktop-label"> prices</span></span><ArrowRight size={19} /></>}</button>
      {showSuggestions && options.length > 0 && <div className="search-suggestions">
        <div className="suggestion-label">{value ? 'Suggested searches' : history.length ? 'Recent & popular searches' : 'A little inspiration'}</div>
        {options.map((item, index) => <button type="button" className={highlight === index ? 'highlighted' : ''} key={item} onMouseDown={event => event.preventDefault()} onClick={() => choose(item)}><Search size={16} /><span>{item}</span><ArrowUpRight size={16} /></button>)}
      </div>}
    </form>
    {error && <p className="form-error" role="alert"><AlertCircle size={15} />{error}</p>}
  </div>;
}

function SourcePills({ sources = [], onClick }) {
  const checked = sources.filter(source => ['ok', 'empty'].includes(source.status)).length;
  const priced = sources.filter(source => source.status === 'ok').length;
  return <button className="source-pills multi-source-pills" onClick={onClick} aria-label="View retailer connection status" title={STORES.map(store => `${storeName(store)}: ${sources.find(source => source.store === store)?.status || 'not checked'}`).join(' · ')}>
    <span><i className={priced ? 'dot green' : 'dot neutral'} /><span>{checked ? `${checked} of ${STORES.length} stores checked` : `${STORES.length} retailer connections`}</span>{checked === STORES.length && <Check size={12} />}</span><Info size={14} />
  </button>;
}
function SourceNotice({ sources = [], query, onDetails }) {
  const unavailable = sources.filter(source => !['ok', 'empty', 'unknown'].includes(source.status));
  if (!unavailable.length) return null;
  const allUnavailable = unavailable.length === STORES.length;
  return <div className="source-notice" role="status"><Info size={18} strokeWidth={1.8} /><div><strong>{allUnavailable ? 'The retailers could not return prices right now.' : `${unavailable.length} retailer connection${unavailable.length > 1 ? 's are' : ' is'} temporarily unavailable.`}</strong><span>{allUnavailable ? ' Missing prices are never estimated.' : ' Available store prices are still shown. We never guess the missing ones.'}</span></div><div className="notice-actions"><button onClick={onDetails}>Source details<CircleHelp size={14} /></button></div></div>;
}
function ProductCard({ product, sources, saved, onSave, onOpen, listView = false, snapshot = false, preferredStore = 'all' }) {
  const entries = offerEntries(product);
  const multi = entries.length > 1;
  const selected = entries.find(([store]) => store === preferredStore);
  const visible = selected ? [selected, ...entries.filter(([store]) => store !== preferredStore).slice(0, 2)] : entries.slice(0, 3);
  const eligible = entries.filter(([, offer]) => offer.available === true).length;
  const stale = Date.now() - new Date(product.checkedAt).getTime() > 180000;
  return <article className={`product-card ${listView ? 'list-card' : ''}`}>
    <div className="product-photo"><span className={`product-tag ${multi ? 'two-prices' : ''}`}>{multi ? `${entries.length} store prices` : `${storeMeta(entries[0]?.[0]).shortName} listing`}</span><button className={`save-product ${saved ? 'is-saved' : ''}`} onClick={() => onSave(product)} aria-label={`${saved ? 'Remove' : 'Save'} ${product.title}`} aria-pressed={saved}><Heart size={18} fill={saved ? 'currentColor' : 'none'} strokeWidth={1.7} /></button><button className="product-image-button" onClick={() => onOpen(product)} aria-label={`Compare ${product.title}`}><ProductImage product={product} /></button></div>
    <div className="product-content"><div className="product-meta"><span className="brand">{product.brand}</span>{typeof product.rating === 'number' && <span className="rating" title={`${product.rating} out of 5 from ${storeName(product.ratingSource)}`}><Star size={12} fill="currentColor" strokeWidth={0} />{product.rating.toFixed(1)}{Number(product.ratingCount) > 0 && <span>({Number(product.ratingCount).toLocaleString('en-AE')})</span>}</span>}</div><button className="product-title-button" onClick={() => onOpen(product)}><h3>{product.title}</h3></button>
      <div className="price-rows">{visible.map(([store, offer]) => <div className={`price-row ${product.lowestStores?.includes(store) && product.priceDifference > 0 || product.lowerStore === store ? 'lower-price' : ''}`} key={store}><StoreLogo store={store} /><span className={`listed-price ${offer.available === false ? 'out-of-stock-price' : ''}`}><Amount value={offer.price} />{offer.available === false ? <span className="stock-caption">Out of stock</span> : offer.available !== true && <span className="stock-caption">Check stock</span>}</span></div>)}</div>
      <button className="more-store-prices" onClick={() => onOpen(product)}>{entries.length > 3 ? `+ ${entries.length - 3} more store price${entries.length - 3 > 1 ? 's' : ''}` : multi ? 'See listings & stock details' : 'Check other retailer matches'}<ArrowRight size={12} /></button>
      <div className="price-note"><span className={`dot ${eligible > 1 ? 'green' : 'neutral'}`} />{eligible > 1 && product.priceDifference !== null ? product.priceDifference ? `AED ${money(product.priceDifference)} available-price gap` : 'Same available listed price' : multi ? 'Stock differs · review the listings' : 'One price found · more stores checked'}{multi && product.match.level !== 'verified' && <span className="review-label"> · Check variant</span>}</div>
      <div className="product-card-footer"><span title={fullDate(product.checkedAt)} className={stale ? 'stale' : ''}>{snapshot ? 'Saved price · ' : ''}{stale ? 'Last checked' : 'Checked'} {ago(product.checkedAt)}</span><button onClick={() => onOpen(product)}>Compare<ArrowUpRight size={16} /></button></div>
    </div>
  </article>;
}
function SkeletonGrid() {
  return <div className="product-grid" aria-label="Loading live product prices" aria-busy="true">{[0, 1, 2, 3].map(item => <div className="skeleton-card" key={item}><div className="skeleton-photo shimmer" /><div className="skeleton-body"><div className="shimmer skeleton-line short" /><div className="shimmer skeleton-line" /><div className="shimmer skeleton-line" /><div className="skeleton-prices shimmer" /><div className="shimmer skeleton-line" /></div></div>)}</div>;
}

function Modal({ title, children, onClose, className = '' }) {
  const panel = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.focus();
    function keyboard(event) {
      if (event.key === 'Escape') close.current();
      if (event.key === 'Tab') {
        const focusable = [...panel.current.querySelectorAll('button:not([disabled]), a[href], input, select, [tabindex="0"]')].filter(el => el.offsetParent !== null);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { event.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener('keydown', keyboard);
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', keyboard); previous?.focus?.({ preventScroll: true }); };
  }, []);
  return <div className="modal-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={`modal-panel ${className}`} ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-heading"><span className="modal-eyebrow"><Logo small /></span><button className="modal-close icon-button" onClick={onClose} aria-label="Close dialog"><X size={22} /></button></div>
      <h2 id="modal-title">{title}</h2>
      {children}
    </section>
  </div>;
}
function DetailContent({ product, onSave, saved, onRecheck, onCopy, sources }) {
  const entries = offerEntries(product);
  const multi = entries.length > 1;
  const missing = STORES.filter(store => !product.offers[store]);
  return <>
    <div className="detail-top"><div className="detail-photo"><ProductImage product={product} /></div><div className="detail-summary"><span className="eyebrow">{product.category} · {product.brand}</span><h3 title={product.title}>{product.title}</h3><div className="detail-actions"><button className={`secondary-button ${saved ? 'saved-button' : ''}`} onClick={() => onSave(product)}><Heart size={16} fill={saved ? 'currentColor' : 'none'} />{saved ? 'Saved to shortlist' : 'Save to shortlist'}</button><button className="icon-button outlined" onClick={() => onCopy(product)} aria-label="Copy comparison link"><Copy size={16} /></button></div><span className="checked-detail"><Clock3 size={14} />{entries.length} store price{multi ? 's' : ''} · Last checked {fullDate(product.checkedAt)}</span></div></div>
    <div className={`match-note ${multi ? '' : 'single-note'}`}><ShieldCheck size={20} /><div><strong>{multi ? product.match.level === 'verified' ? 'Shared product barcode across these listings' : 'Likely product matches — review the variants' : 'One retailer price found so far'}</strong><p>{multi ? product.match.level === 'verified' ? 'The listings share a valid product barcode. Check seller, delivery and warranty before buying.' : 'Known model and variant conflicts were rejected, but missing specifications are not verified. Compare storage, color, region, condition, warranty and bundle details.' : 'A missing match does not prove the product is unavailable at another retailer. Prices are never estimated.'}</p></div></div>
    <div className="comparison-table"><div className="comparison-table-head"><span>Retailer</span><span>Listed price</span><span>Stock & seller</span><span>Shop directly</span></div>{entries.map(([store, offer]) => <div className={`comparison-offer ${product.lowestStores?.includes(store) && product.priceDifference > 0 || product.lowerStore === store ? 'offer-lower' : ''}`} key={store}>
      <div className="comparison-retailer"><StoreLogo store={store} large /><span className="offer-time">Retrieved {ago(offer.checkedAt)}</span>{(product.lowestStores?.includes(store) || product.lowerStore === store) && product.priceDifference > 0 && <span className="offer-badge"><ArrowDown size={11} />Lowest listed price</span>}</div>
      <div className="comparison-price"><Amount value={offer.price} className="detail-amount" />{offer.originalPrice && <span className="reference-price"><s>AED {money(offer.originalPrice)}</s> store reference</span>}</div>
      <div className="comparison-listing"><span className={`stock-status ${offer.available === true ? 'in-stock' : offer.available === false ? 'not-in-stock' : 'unknown-stock'}`}><span className={`dot ${offer.available === true ? 'green' : offer.available === false ? 'amber' : 'neutral'}`} />{offer.available === true ? 'Retailer reports in stock' : offer.available === false ? 'Out of stock' : 'Confirm availability'}</span>{offer.seller && <span className="offer-seller">Seller: {offer.seller}</span>}<details className="quote-details"><summary>Listing details<ChevronDown size={12} /></summary><p>{offer.title}</p>{Object.entries(offer.specs || {}).slice(0, 3).map(([key, value]) => <span key={key}>{key}: {String(value)}</span>)}<span>{offer.priceSource || 'Retailer catalog'} · {fullDate(offer.checkedAt)}</span></details></div>
      <a className={`store-button ${store}`} href={offer.url} target="_blank" rel="noopener noreferrer">{offer.available === false ? 'Check store' : 'View store'}<ArrowUpRight size={16} /></a>
    </div>)}</div>
    {product.priceDifference > 0 && <div className="difference-summary">Available listed-price gap <strong>AED {money(product.priceDifference)}</strong><span>Highest minus lowest in-stock listing · not a guaranteed saving</span></div>}
    {missing.length > 0 && <details className="missing-retailers"><summary>{missing.length} other retailer{missing.length > 1 ? 's' : ''}: no matching price returned<ChevronDown size={15} /></summary><div>{missing.map(store => <div key={store}><StoreLogo store={store} /><span>{sources?.find(source => source.store === store)?.status === 'blocked' || sources?.find(source => source.store === store)?.status === 'error' ? 'Source temporarily unavailable' : 'No sufficiently similar priced listing'}</span><a href={searchUrl(store, product.searchTerm || product.title)} target="_blank" rel="noopener noreferrer">Search store<ArrowUpRight size={13} /></a></div>)}</div></details>}
    <div className="detail-bottom"><p><Info size={15} />Listed prices only. Out-of-stock or unconfirmed-stock offers are excluded from the gap. Shipping, coupons, warranties and regional versions can change the value. Confirm checkout totals.</p><button className="text-button" onClick={() => onRecheck(product)}><RefreshCw size={15} />Recheck this product</button></div>
  </>;
}
function SourcesContent({ health, sources }) {
  return <>
    <p className="modal-intro">One search, {STORES.length} UAE storefronts. Real retailer listings, never sample prices.</p>
    <div className="source-detail-list multi-source-details">{STORES.map(store => {
      const source = sources?.find(item => item.store === store) || health?.sources?.find(item => item.store === store);
      const ok = source?.status === 'ok';
      return <div className="source-detail" key={store}><div className="source-detail-top"><StoreLogo store={store} large /><span className={`connection-badge ${ok ? 'connected' : ''}`}><span className={`dot ${ok ? 'green' : 'amber'}`} />{ok ? `${source.itemCount} priced listings` : source?.status === 'unknown' || !source ? 'Not checked yet' : source.status === 'empty' ? 'No priced results' : 'Unavailable'}</span></div><p>{source?.message || 'Run a product search to check this retailer.'}</p><div className="source-detail-meta"><span>{storeMeta(store).source}</span><span>Checked {ago(source?.checkedAt)}</span></div></div>;
    })}</div>
    <div className="provider-box"><div><Database size={21} /><h3>Direct storefront connections</h3></div><p>The backend reads the public catalog or product pages used by these retailers. No personal API key or paid-provider account is required for the current direct connections. Retailer scripts and tracking are not loaded in your browser.</p><ol><li>All {STORES.length} retailer searches run in the background from one query.</li><li>AED prices and stock are read from real listings or concrete product variants.</li><li>Every pair in a multi-store group is checked for known model, color, storage, region, generation, pack and quantity conflicts.</li><li>Unknown stock stays unknown. Only in-stock listings are used to calculate a price gap.</li></ol><span className="provider-status provider-connected"><span className="dot green" />No made-up prices. No retailer account required to compare.</span></div>
    <p className="small-print"><ShieldCheck size={14} />Search snapshots are cached for up to 3 minutes. Each price has its own retrieval time. Retailer access can change; title-based matches are likely, not verified identical. Check delivery, warranty and final totals.</p>
  </>;
}
function HowContent() {
  const steps = [
    { icon: Search, title: 'Tell us what’s on your list.', body: 'Search a product name or exact model. Specific searches give you more useful matches.' },
    { icon: SlidersHorizontal, title: 'Give the prices a second look.', body: 'See available prices from the connected UAE stores together. Missing prices and uncertain matches are clearly labeled.' },
    { icon: ShoppingBag, title: 'Pick your store. Shop your way.', body: 'Open the retailer to check delivery, seller and the final total. You buy directly from the store, not from Pricewise.' },
  ];
  return <><p className="modal-intro">Less tab hopping. More confident shopping.</p><div className="how-steps">{steps.map((step, index) => <div key={step.title}><span className="step-icon"><step.icon size={25} strokeWidth={1.6} /></span><div><span className="step-number">0{index + 1}</span><h3>{step.title}</h3><p>{step.body}</p></div></div>)}</div><div className="faq-list"><details><summary>Are these the final checkout prices?<ChevronDown size={16} /></summary><p>No. We show listed product prices in AED. Delivery charges, coupons, memberships, regional versions, warranties and seller conditions can change the final total.</p></details><details><summary>Why is one store’s price missing?<ChevronDown size={16} /></summary><p>The store may have blocked a request, timed out, returned no priced results, or we may not have found a sufficiently similar listing. We never invent a price to fill a gap.</p></details><details><summary>Are product matches always exact?<ChevronDown size={16} /></summary><p>No. Title-based matches are labeled “likely.” We reject known model, capacity, color, condition and region differences, but you should still compare the full listings. Only shared product barcodes are labeled verified.</p></details></div></>;
}

export default function App() {
  const initial = useRef(new URLSearchParams(window.location.search)).current;
  const initialQuery = (initial.get('q') || '').slice(0, 120);
  const [page, setPage] = useState(initial.get('view') === 'saved' ? 'saved' : initialQuery.length >= 2 ? 'compare' : 'home');
  const [input, setInput] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery);
  const [data, setData] = useState(null);
  const [featured, setFeatured] = useState(null);
  const [loading, setLoading] = useState(false);
  const [featuredLoading, setFeaturedLoading] = useState(initialQuery.length < 2 && initial.get('view') !== 'saved');
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [health, setHealth] = useState(null);
  const [saved, setSaved] = useState(savedSnapshots);
  const [history, setHistory] = useState(() => readStorage('pricewise:history', []).filter(item => typeof item === 'string').slice(0, 8));
  const [modal, setModal] = useState(null);
  const [toast, setToast] = useState(null);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [featuredTab, setFeaturedTab] = useState('All picks');
  const [category, setCategory] = useState('All categories');
  const [storeFilter, setStoreFilter] = useState('all');
  const [sort, setSort] = useState('relevance');
  const [view, setView] = useState('grid');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [maxPrice, setMaxPrice] = useState('');
  const [goodRating, setGoodRating] = useState(false);
  const [, tick] = useState(0);
  const inputRef = useRef(null);
  const requestRef = useRef(null);
  const sequence = useRef(0);
  const toastTimer = useRef(null);
  const started = useRef(false);
  const historyRef = useRef(history);
  const featuredRef = useRef(featured);
  const featuredPending = useRef(false);
  historyRef.current = history;
  featuredRef.current = featured;

  function notify(message, isError = false) {
    clearTimeout(toastTimer.current);
    setToast({ message, isError });
    toastTimer.current = setTimeout(() => setToast(null), 3500);
  }
  function updateURL(nextPage, nextQuery = '') {
    const url = new URL(window.location.href);
    url.search = nextPage === 'saved' ? '?view=saved' : nextQuery ? `?q=${encodeURIComponent(nextQuery)}` : '';
    if (url.href !== window.location.href) window.history.pushState({}, '', url);
  }
  function resetFilters() { setStoreFilter('all'); setSort('relevance'); setMaxPrice(''); setGoodRating(false); }
  async function loadFeatured() {
    if (featuredPending.current) return;
    featuredPending.current = true;
    setFeaturedLoading(true);
    try { setFeatured(await getJSON('/api/featured')); }
    catch (err) { setFeatured({ products: [], sources: [], error: err.message }); }
    finally { featuredPending.current = false; setFeaturedLoading(false); }
  }
  function goHome() {
    sequence.current += 1;
    requestRef.current?.abort();
    setLoading(false); setPage('home'); setInput(''); setQuery(''); setFormError(''); setError(''); setCategory('All categories'); setMobileMenu(false); setModal(null);
    updateURL('home');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (!featured || featured.error || Date.now() - new Date(featured.checkedAt).getTime() > 180000) loadFeatured();
  }
  function goSaved() {
    sequence.current += 1; requestRef.current?.abort(); setLoading(false);
    resetFilters(); setPage('saved'); setMobileMenu(false); setModal(null); setError(''); setFormError(''); updateURL('saved'); window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  async function runSearch(value, refresh = false, scroll = true, recordURL = true) {
    const term = value.trim().replace(/\s+/g, ' ');
    if (term.length < 2 || !/[\p{L}\p{N}]/u.test(term)) { setFormError('Add a product name or model — at least 2 characters.'); inputRef.current?.focus(); return; }
    requestRef.current?.abort();
    const controller = new AbortController(); requestRef.current = controller;
    const id = ++sequence.current;
    setPage('compare'); setInput(term); setQuery(term); setLoading(true); setError(''); setFormError(''); setModal(null); setMobileMenu(false); setData(null);
    if (!refresh) resetFilters();
    if (recordURL) updateURL('compare', term);
    if (scroll) window.scrollTo({ top: 0, behavior: 'smooth' });
    const recent = [term, ...historyRef.current.filter(item => item.toLowerCase() !== term.toLowerCase())].slice(0, 8);
    historyRef.current = recent;
    setHistory(recent); writeStorage('pricewise:history', recent);
    try {
      const result = await getJSON(`/api/search?q=${encodeURIComponent(term)}${refresh ? '&refresh=true' : ''}`, controller.signal);
      if (sequence.current === id) {
        setData(result);
        setSaved(current => {
          if (!current.length || !Array.isArray(result.products)) return current;
          const freshById = new Map(result.products.map(item => [item.id, item]));
          let changed = false;
          const updated = current.map(item => {
            const fresh = freshById.get(item.id);
            if (!fresh) return item;
            changed = true;
            return normalizeSavedProduct({ ...fresh, savedAt: item.savedAt || new Date().toISOString() });
          });
          if (changed) writeStorage('pricewise:saved', updated);
          return changed ? updated : current;
        });
      }
    } catch (err) {
      if (err.name !== 'AbortError' && sequence.current === id) setError(err.message);
    } finally { if (sequence.current === id) setLoading(false); }
  }
  useEffect(() => {
    if (!started.current) {
      started.current = true;
      getJSON('/api/health').then(setHealth).catch(() => {});
      if (initialQuery.length < 2 && initial.get('view') !== 'saved') loadFeatured();
      if (initialQuery.length >= 2 && initial.get('view') !== 'saved') runSearch(initialQuery, false, false, false);
    }
    const interval = setInterval(() => tick(value => value + 1), 30000);
    function keyboard(event) {
      if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) && !document.querySelector('[role="dialog"]')) { event.preventDefault(); inputRef.current?.focus(); }
    }
    function pop() {
      const params = new URLSearchParams(window.location.search);
      if (params.get('q') && params.get('view') !== 'saved') runSearch(params.get('q').slice(0, 120), false, false, false);
      else {
        sequence.current += 1; requestRef.current?.abort(); setLoading(false); setError(''); setFormError(''); resetFilters();
        setPage(params.get('view') === 'saved' ? 'saved' : 'home');
        if (params.get('view') !== 'saved') {
          setInput(''); setQuery('');
          if (!featuredRef.current || Date.now() - new Date(featuredRef.current.checkedAt).getTime() > 180000) loadFeatured();
        }
      }
      setModal(null);
    }
    document.addEventListener('keydown', keyboard); window.addEventListener('popstate', pop);
    return () => { clearInterval(interval); document.removeEventListener('keydown', keyboard); window.removeEventListener('popstate', pop); };
  }, []);
  useEffect(() => { document.title = page === 'saved' ? 'Your shortlist — Pricewise' : query && page === 'compare' ? `${query} — UAE price comparison | Pricewise` : 'Pricewise — Same product. Smarter price.'; }, [page, query]);

  function toggleSave(product) {
    const exists = saved.some(item => item.id === product.id);
    if (!exists && saved.length >= 60) { notify('Your shortlist is full. Remove a product to save another.', true); return; }
    const next = exists ? saved.filter(item => item.id !== product.id) : [{ ...product, savedAt: new Date().toISOString() }, ...saved];
    setSaved(next);
    const persisted = writeStorage('pricewise:saved', next);
    notify(!persisted ? 'Saved for this session. Browser storage is unavailable.' : exists ? 'Removed from your shortlist.' : 'A good find, saved to your shortlist.');
  }
  function openSources() {
    setModal({ type: 'sources' });
    getJSON('/api/health').then(setHealth).catch(() => {});
  }
  const sources = page === 'compare' ? data?.sources || health?.sources || [] : featured?.sources || health?.sources || [];
  const displayedProducts = useMemo(() => {
    let products = page === 'saved' ? [...saved] : page === 'home' ? [...(featured?.products || [])] : [...(data?.products || [])];
    if (page === 'home') return featuredTab === 'All picks' ? products : products.filter(product => product.category === featuredTab);
    products = products.filter(product => (storeFilter === 'all' || storeFilter === 'both' && offerEntries(product).length >= 2 || STORES.includes(storeFilter) && product.offers[storeFilter])
      && (!maxPrice || priceValue(product, storeFilter) <= Number(maxPrice)) && (!goodRating || product.rating >= 4));
    if (sort === 'price-asc') products.sort((a, b) => priceValue(a, storeFilter) - priceValue(b, storeFilter));
    if (sort === 'price-desc') products.sort((a, b) => priceValue(b, storeFilter) - priceValue(a, storeFilter));
    if (sort === 'rating') products.sort((a, b) => (b.rating || 0) - (a.rating || 0));
    return products;
  }, [page, data, saved, featured, featuredTab, storeFilter, sort, maxPrice, goodRating]);
  async function copyComparison(product) {
    try { await navigator.clipboard.writeText(`${window.location.origin}/?q=${encodeURIComponent(product.searchTerm || product.title)}`); notify('Comparison search link copied.'); }
    catch { notify('Copy isn’t available here. You can share the page address instead.', true); }
  }
  function exportCSV() {
    const csvCell = value => {
      let text = String(value ?? '');
      if (/^[=+\-@]/.test(text)) text = `'${text}`;
      return `"${text.replace(/"/g, '""')}"`;
    };
    const rows = [['Product', 'Match confidence', ...RETAILERS.flatMap(store => [`${store.name} AED`, `${store.name} in stock`, `${store.name} checked at`, `${store.name} URL`])],
      ...displayedProducts.map(product => [product.title, product.match.level, ...STORES.flatMap(store => [product.offers[store]?.price, product.offers[store]?.available, product.offers[store]?.checkedAt, product.offers[store]?.url])])];
    const blob = new Blob(['\uFEFF' + rows.map(row => row.map(csvCell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `pricewise-${query || 'shortlist'}.csv`; link.click(); URL.revokeObjectURL(url); notify('Your comparison has been exported.');
  }
  const savedIds = new Set(saved.map(item => item.id));
  const searching = page === 'compare' && loading;
  const modalSources = sources;

  const searchForm = <SearchForm value={input} onChange={value => { setInput(value); setFormError(''); }} onSearch={runSearch} loading={searching} history={history} inputRef={inputRef} error={formError} compact={page !== 'home'} />;
  function filters() {
    return <>
      <div className="results-toolbar"><div className="store-filters" aria-label="Filter by store">{[['all', 'All listings', 'Show every returned product listing'], ['both', '2+ stores', 'Show products matched across 2 or more stores'], ...RETAILERS.map(store => [store.id, store.shortName, `Show listings with a ${store.name} price`])].map(([key, label, hint]) => <button key={key} className={storeFilter === key ? 'active' : ''} title={hint} aria-label={`${label}: ${hint}`} onClick={() => setStoreFilter(key)}>{label}</button>)}</div><div className="toolbar-right"><button className={`filter-button ${filtersOpen || maxPrice || goodRating ? 'active' : ''}`} onClick={() => setFiltersOpen(!filtersOpen)} aria-expanded={filtersOpen}><SlidersHorizontal size={16} /><span>Filters</span>{(maxPrice || goodRating) && <i className="dot green" />}</button><div className="sort-select"><select aria-label="Sort products" value={sort} onChange={event => setSort(event.target.value)}><option value="relevance">Most relevant</option><option value="price-asc">Price: low to high</option><option value="price-desc">Price: high to low</option><option value="rating">Highest rated</option></select><ChevronDown size={14} /></div><div className="view-toggle"><button className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')} aria-label="Grid view" aria-pressed={view === 'grid'}><LayoutGrid size={16} /></button><button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')} aria-label="List view" aria-pressed={view === 'list'}><List size={18} /></button></div></div></div>
      {filtersOpen && <div className="filter-panel"><label>Maximum listed price <div className="max-price-input"><span>AED</span><input type="number" min="0" max="999999" placeholder="Any price" value={maxPrice} onChange={event => setMaxPrice(event.target.value === '' ? '' : String(Math.max(0, Math.min(999999, Number(event.target.value)))))} aria-label="Maximum price in AED" /></div></label><label className="check-filter"><input type="checkbox" checked={goodRating} onChange={event => setGoodRating(event.target.checked)} /><Star size={15} />Rated 4 stars & above</label><button className="text-button" onClick={resetFilters}>Reset filters<X size={14} /></button></div>}
    </>;
  }

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="site-header"><div className="container header-inner"><button className="logo-button" onClick={goHome} aria-label="Pricewise home"><Logo /></button><nav className={mobileMenu ? 'nav-open' : ''} aria-label="Main navigation"><button className={page !== 'saved' ? 'active' : ''} onClick={goHome}>Compare prices</button><button className={page === 'saved' ? 'active' : ''} onClick={goSaved}>Saved finds{saved.length > 0 && <span className="nav-count">{saved.length}</span>}</button><button onClick={() => { setModal({ type: 'how' }); setMobileMenu(false); }}>How it works<ArrowUpRight size={12} /></button></nav><div className="header-actions"><button className="region-button" onClick={() => setModal({ type: 'region' })}><Flag /><span>UAE <span className="region-dot">·</span> AED</span><ChevronDown size={13} /></button><div className="header-divider" /><button className="shortlist-button" onClick={goSaved}><Heart size={17} strokeWidth={1.7} /><span>My shortlist</span>{saved.length > 0 && <span className="shortlist-count">{saved.length}</span>}</button><button className="mobile-menu-button icon-button" onClick={() => setMobileMenu(!mobileMenu)} aria-label="Toggle navigation" aria-expanded={mobileMenu}>{mobileMenu ? <X size={23} /> : <Menu size={23} />}</button></div></div></header>
    <main id="main" className="container">
      {page === 'home' ? <>
        <section className="hero"><div className="hero-copy"><span className="eyebrow hero-eyebrow"><span className="little-spark">✳</span>A LITTLE SEARCH. A LOT OF SAVINGS.</span><h1>Same product.<br /><span>Smarter price.</span></h1><p>The things you love, for a little less.<br />Compare prices across {STORES.length} UAE stores in one simple search.</p>{searchForm}<div className="popular-searches"><span>Try searching</span>{['AirPods Pro 3', 'iPhone 16', 'Sony headphones'].map(term => <button key={term} onClick={() => runSearch(term)}>{term}<ArrowUpRight size={12} /></button>)}</div><div className="hero-store-line"><span>YOUR FAVORITE STORES, SIDE BY SIDE</span><div className="hero-retailer-logos">{STORES.map(store => <StoreLogo key={store} store={store} />)}</div></div></div><div className="hero-visual"><div className="hero-orbit" /><img className="hero-image" src="/hero-headphones.webp" alt="Editorial illustration of silver over-ear headphones" /><div className="floating-store jumbo-float"><span>A second look at</span><StoreLogo store="jumbo" large /><ArrowUpRight size={16} /></div><div className="floating-store noon-float"><span>Find it on</span><StoreLogo store="noon" large /><ArrowUpRight size={16} /></div><div className="hero-sticker"><svg viewBox="0 0 120 120" aria-hidden="true"><path d="m60 0 10 13 15-7 4 16 16-1-2 17 15 6-10 13 12 12-15 8 4 16-17 1-2 17-16-5-8 14-12-11-13 10-6-16-17 2 1-16-16-5 7-15-13-10 13-10-7-15 16-4-1-16 17 2 6-15 13 10Z" fill="#f3d783" /></svg><span>less browsing.<br />more living.<Leaf size={17} strokeWidth={1.6} /></span></div><span className="visual-caption">GOOD FINDS START WITH A SECOND LOOK.</span></div></section>
        <div className="trust-row"><div><span className="trust-icon"><SlidersHorizontal size={20} strokeWidth={1.6} /></span><p><strong>{STORES.length} stores. One search.</strong><span>Less tab hopping, more clarity.</span></p></div><div><span className="trust-icon"><ShieldCheck size={21} strokeWidth={1.6} /></span><p><strong>Real prices. No guesswork.</strong><span>Missing data is always labeled.</span></p></div><div><span className="trust-icon"><ShoppingBag size={20} strokeWidth={1.6} /></span><p><strong>Shop directly with the store.</strong><span>Your purchase, on your terms.</span></p></div></div>
        <section className="category-section" aria-label="Browse by category"><div className="category-caption"><span>WHAT’S ON YOUR LIST?</span><span>A good place to start <ArrowDown size={13} /></span></div><div className="category-row">{CATEGORIES.map(item => <button className={category === item.label ? 'active' : ''} key={item.label} onClick={() => { setCategory(item.label); item.query ? runSearch(item.query) : goHome(); }}><item.icon size={18} strokeWidth={1.6} />{item.label}</button>)}</div></section>
        <section className="featured-section"><div className="section-heading"><div><span className="eyebrow section-eyebrow">THE SMART SHOPPING EDIT</span><h2>A few favorites. A better way to browse.</h2><p>Popular picks, with real prices from the stores we can reach.</p></div><button className="text-button explore-button" onClick={() => runSearch('electronics')}>Explore more<ArrowUpRight size={18} /></button></div><div className="featured-tools"><div className="featured-tabs">{['All picks', 'Audio', 'Phones', 'Wearables'].map(tab => <button className={featuredTab === tab ? 'active' : ''} key={tab} onClick={() => setFeaturedTab(tab)}>{tab}</button>)}</div>{!featuredLoading && <SourcePills sources={featured?.sources} onClick={openSources} />}</div>{featuredLoading ? <><div className="loading-caption"><span className="dot green pulse" />Checking the retailers for real prices…</div><SkeletonGrid /></> : <><SourceNotice sources={featured?.sources} onDetails={openSources} />{displayedProducts.length ? <div className="product-grid">{displayedProducts.map(product => <ProductCard key={product.id} product={product} sources={featured?.sources} saved={savedIds.has(product.id)} onSave={toggleSave} onOpen={product => setModal({ type: 'product', product })} />)}</div> : <div className="empty-state compact-empty"><PackageSearch size={35} strokeWidth={1.4} /><h3>{featured?.error ? 'The live catalog is taking a break.' : 'No live picks in this category yet.'}</h3><p>{featured?.error || 'Try a specific product search to check the stores.'}</p><button className="secondary-button" onClick={() => featured?.error ? loadFeatured() : setFeaturedTab('All picks')}>{featured?.error ? 'Try again' : 'View all picks'}<ArrowRight size={15} /></button></div>}</>}
        </section>
        <section className="second-look"><div><span className="eyebrow">A SMALL HABIT. A SMARTER PURCHASE.</span><h2>Good shopping starts<br />with a second look.</h2><p>Find it. Compare it. Make it yours — without the extra tabs.</p><button className="dark-button" onClick={() => setModal({ type: 'how' })}>Meet your new shopping habit<ArrowUpRight size={17} /></button></div><div className="second-look-steps"><div><span>01</span><Search size={20} strokeWidth={1.6} /><p>Search what<br />you have in mind.</p></div><div><span>02</span><SlidersHorizontal size={20} strokeWidth={1.6} /><p>Give the prices<br />a second look.</p></div><div><span>03</span><ShoppingBag size={20} strokeWidth={1.6} /><p>Choose a store.<br />Shop with confidence.</p></div></div></section>
      </> : <>
        <section className="search-intro"><div className="intro-copy"><span className="eyebrow"><span className="little-spark">✳</span>{page === 'saved' ? 'GOOD FINDS DESERVE A PLACE OF THEIR OWN.' : 'YOUR SMARTER SHOPPING STARTS HERE.'}</span><h1>{page === 'saved' ? 'Your shortlist. Your next good find.' : 'Let’s find your better price.'}</h1><p>{page === 'saved' ? 'The products you’ve saved, all in one place. No account needed.' : 'Search once. See the available prices. Choose with confidence.'}</p></div>{searchForm}</section>
        <section className="results-section" aria-live="polite"><div className="results-heading"><div><h2>{page === 'saved' ? <>Saved finds<span className="result-count">{saved.length}</span></> : <>Results for <span>“{query}”</span></>}</h2><p>{searching ? 'Checking live retailer catalogs…' : page === 'saved' ? 'Saved on this browser. Recheck a product before buying.' : data ? `${displayedProducts.length} of ${data.products.length} listings${data.cached ? ' · Recently checked prices' : ' · Retailer prices in AED'}` : error ? 'No prices are shown until the search succeeds.' : 'Enter a product to get started.'}</p></div><div className="results-heading-actions">{page === 'compare' && data && <SourcePills sources={data.sources} onClick={openSources} />}{displayedProducts.length > 0 && <button className="icon-button outlined" onClick={exportCSV} aria-label="Export comparison as CSV" title="Export CSV"><Download size={17} /></button>}{page === 'compare' && <button className="icon-button outlined" disabled={loading} onClick={() => runSearch(query, true)} aria-label="Refresh prices" title="Refresh prices"><RefreshCw size={17} className={loading ? 'spin' : ''} /></button>}</div></div>
        {page === 'saved' && saved.length === 0 ? <div className="empty-state saved-empty"><span className="empty-illustration"><Heart size={43} strokeWidth={1.25} /><span className="empty-star">✳</span></span><span className="eyebrow">A LITTLE COLLECTION OF GOOD FINDS</span><h2>Love it? Keep it close.</h2><p>Tap the heart on any product to save it here.<br />Your next purchase deserves a little consideration.</p><button className="dark-button" onClick={goHome}>Find something worth saving<ArrowRight size={17} /></button></div> : <>
          {filters()}
          {page === 'compare' && !loading && <SourceNotice sources={data?.sources} query={query} onDetails={openSources} />}
          {searching ? <><div className="loading-caption"><span className="dot green pulse" />Checking {STORES.length} UAE retailers for current listings. No sample prices, ever.</div><SkeletonGrid /></> : error && page === 'compare' ? <div className="empty-state error-state"><AlertCircle size={39} strokeWidth={1.4} /><h3>Let’s give that another try.</h3><p>{error}</p><button className="dark-button" onClick={() => runSearch(query, true)}>Try again<RefreshCw size={16} /></button><div className="direct-store-links">{STORES.map(store => <a key={store} href={searchUrl(store, query)} target="_blank" rel="noopener noreferrer">Search {storeMeta(store).shortName}<ArrowUpRight size={14} /></a>)}</div></div> : displayedProducts.length ? <div className={`product-grid ${view === 'list' ? 'list-view' : ''}`}>{displayedProducts.map(product => <ProductCard key={product.id} product={product} sources={sources} saved={savedIds.has(product.id)} onSave={toggleSave} onOpen={product => setModal({ type: 'product', product })} listView={view === 'list'} snapshot={page === 'saved'} preferredStore={storeFilter} />)}</div> : <div className="empty-state"><PackageSearch size={40} strokeWidth={1.4} /><h3>{storeFilter !== 'all' || maxPrice || goodRating ? 'No listings match these filters.' : data?.sources?.every(source => ['blocked', 'error'].includes(source.status)) ? 'The stores couldn’t return live prices.' : 'No priced listings found.'}</h3><p>{storeFilter === 'both' ? 'Multi-store matches need at least two retailer prices. Try all listings or check source status.' : 'Try a more specific model, a different product name, or fewer filters.'}</p><button className="secondary-button" onClick={() => { resetFilters(); if (data?.products.length === 0) inputRef.current?.focus(); }}>Reset filters & try again<ArrowRight size={16} /></button>{page === 'compare' && <div className="direct-store-links">{STORES.map(store => <a key={store} href={searchUrl(store, query)} target="_blank" rel="noopener noreferrer">Search {storeMeta(store).shortName}<ArrowUpRight size={14} /></a>)}</div>}</div>}
          {page === 'compare' && data && !loading && <div className="results-footnote"><Info size={15} /><p>Listed prices only. Shipping and promotions can change the final total. Title-based matches are not guaranteed identical — review the store listings.</p><span>Search completed {ago(data.checkedAt)}</span></div>}
        </>}
        </section>
      </>}
    </main>
    <footer className="site-footer"><div className="container"><div className="footer-top"><button className="logo-button" onClick={goHome}><Logo small /></button><p>A little search goes a long way.</p><div><button onClick={openSources}>Our data sources<ArrowUpRight size={13} /></button><button onClick={() => setModal({ type: 'privacy' })}>Privacy, simply</button><button onClick={() => setModal({ type: 'how' })}>How it works</button></div></div><div className="footer-bottom"><span>© {new Date().getFullYear()} Pricewise. Made for smarter shopping.</span><span>Independent of the retailers. All prices in AED.<Flag /></span></div></div></footer>
    {toast && <div className={`toast ${toast.isError ? 'toast-error' : ''}`} role="status">{toast.isError ? <Info size={18} /> : <CheckCircle2 size={18} />}{toast.message}<button onClick={() => setToast(null)} aria-label="Dismiss notification"><X size={15} /></button></div>}
    {modal?.type === 'product' && <Modal title="Give it a second look." onClose={() => setModal(null)} className="product-modal"><DetailContent product={modal.product} sources={modalSources} onSave={toggleSave} saved={savedIds.has(modal.product.id)} onRecheck={product => runSearch(product.searchTerm || product.title, true)} onCopy={copyComparison} /></Modal>}
    {modal?.type === 'sources' && <Modal title="A little transparency." onClose={() => setModal(null)} className="sources-modal"><SourcesContent health={health} sources={sources} /></Modal>}
    {modal?.type === 'how' && <Modal title="One small search. A smarter choice." onClose={() => setModal(null)} className="how-modal"><HowContent /></Modal>}
    {modal?.type === 'region' && <Modal title="Made for your kind of shopping." onClose={() => setModal(null)} className="region-modal"><p className="modal-intro">This version compares UAE retailer listings.</p><div className="selected-region"><Flag /><div><strong>United Arab Emirates</strong><span>{STORES.length} connected UAE stores · Prices in AED</span></div><CheckCircle2 size={23} /></div><p className="small-print">Other countries are not connected yet. Prices are listed in AED, not converted from another currency. Delivery and availability depend on your address at the retailer.</p><button className="dark-button" onClick={() => setModal(null)}>Sounds good<Check size={16} /></button></Modal>}
    {modal?.type === 'privacy' && <Modal title="Your shortlist, not your life story." onClose={() => setModal(null)} className="privacy-modal"><p className="modal-intro">No sign-up. No checkout. Just a little help finding your next good purchase.</p><div className="privacy-points"><h3>Saved on your browser</h3><p>Your shortlist and recent searches are stored in your browser’s local storage. They are not synced between devices. Clearing browser data removes them.</p><h3>Searches go to the stores</h3><p>Product queries are sent to this app’s backend and then to public retailer endpoints or the configured data provider. The backend caches search responses for up to 3 minutes.</p><h3>You buy directly</h3><p>Retailer links open the store website, whose own privacy and purchase policies apply. Pricewise does not collect payment details or place orders.</p><h3>No third-party analytics in this build</h3><p>Fonts and interface assets are served locally. Product images are retrieved from approved retailer CDNs through the backend. Hosting may retain standard request logs.</p></div><button className="secondary-button" onClick={() => { setSaved([]); setHistory([]); writeStorage('pricewise:saved', []); writeStorage('pricewise:history', []); notify('Your saved finds and search history have been cleared.'); }}>Clear my local saved data<X size={15} /></button></Modal>}
  </>;
}
