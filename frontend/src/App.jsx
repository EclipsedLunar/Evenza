import React, { useEffect, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronDown,
  Clock3,
  Compass,
  MapPin,
  RotateCw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Users,
  Video,
  X,
} from "lucide-react";

const API_BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

const CATEGORIES = [
  "All",
  "Technology",
  "Academic",
  "Sports",
  "Arts",
  "Entrepreneurship & Business",
  "Communication",
  "Creative Media",
];

const CITIES = [
  "All Maharashtra",
  "Mumbai",
  "Pune",
  "Nagpur",
  "Nashik",
  "Thane",
  "Navi Mumbai",
  "Kolhapur",
  "Solapur",
];

const CATEGORY_IMAGES = {
  Academic: "https://images.unsplash.com/photo-1523580494863-6f3031224c94?auto=format&fit=crop&w=900&q=85",
  Arts: "https://images.unsplash.com/photo-1513364776144-60967b0f800f?auto=format&fit=crop&w=900&q=85",
  Communication: "https://images.unsplash.com/photo-1475721027785-f74eccf877e2?auto=format&fit=crop&w=900&q=85",
  "Creative Media": "https://images.unsplash.com/photo-1492619375914-88005aa9e8fb?auto=format&fit=crop&w=900&q=85",
  "Entrepreneurship & Business": "https://images.unsplash.com/photo-1559136555-9303baea8ebd?auto=format&fit=crop&w=900&q=85",
  Sports: "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?auto=format&fit=crop&w=900&q=85",
  Technology: "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=900&q=85",
};

function formatDate(value) {
  if (!value) return "Date to be announced";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function imageFor(event) {
  return event.image || CATEGORY_IMAGES[event.category] || CATEGORY_IMAGES.Technology;
}

function App() {
  const [events, setEvents] = useState([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [location, setLocation] = useState("All Maharashtra");
  const [mode, setMode] = useState("All");
  const [freeOnly, setFreeOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedEvent, setSelectedEvent] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      if (category !== "All") params.set("category", category);
      if (location !== "All Maharashtra") params.set("location", location);
      if (mode !== "All") params.set("mode", mode);
      if (freeOnly) params.set("max_fee", "0");

      setLoading(true);
      setError("");
      try {
        const response = await fetch(`${API_BASE}/api/events?${params}`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          setError(`The event service returned ${response.status}. Check the backend URL.`);
          return;
        }
        const data = await response.json();
        setEvents(Array.isArray(data) ? data : []);
      } catch (fetchError) {
        if (fetchError.name !== "AbortError") {
          setError("We couldn’t reach the opportunity board. Check your connection and try again.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 220);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [category, freeOnly, location, mode, query, refreshKey]);

  useEffect(() => {
    if (!selectedEvent) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setSelectedEvent(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedEvent]);

  const resetFilters = () => {
    setQuery("");
    setCategory("All");
    setLocation("All Maharashtra");
    setMode("All");
    setFreeOnly(false);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="EVENZA home">
          <span className="brand-mark"><Compass size={21} strokeWidth={2.2} /></span>
          <span className="brand-name">EVENZA<span className="brand-period">.</span></span>
        </a>
        <nav className="top-nav" aria-label="Main navigation">
          <a className="nav-link active" href="#opportunities">Discover</a>
          <a className="nav-link" href="#how-it-works">How it works</a>
        </nav>
        <a className="topbar-cta" href="#opportunities">
          Find your thing <ArrowUpRight size={15} />
        </a>
      </header>

      <main id="top">
        <section className="intro-band" aria-labelledby="page-title">
          <div className="intro-copy">
            <div className="eyebrow"><span className="eyebrow-line" /> DISCOVER. PARTICIPATE. ACHIEVE.</div>
            <h1 id="page-title">Big things start<br /><span>with a first try.</span></h1>
            <p>Competitions, events, and ideas worth showing up for. Your next opportunity is closer than you think.</p>
            <a className="intro-link" href="#opportunities">Explore opportunities <ArrowDownRight size={16} /></a>
          </div>
          <div className="intro-visual" aria-label="Students collaborating at an event">
            <img
              src="https://images.unsplash.com/photo-1528605248644-14dd04022da1?auto=format&fit=crop&w=1400&q=90"
              alt="Students sharing ideas around a table"
            />
            <div className="visual-shade" />
            <div className="visual-note">
              <span className="visual-note-icon"><Sparkles size={16} /></span>
              <span><strong>Your next chapter</strong><small>starts outside the classroom</small></span>
              <ArrowUpRight size={17} className="visual-note-arrow" />
            </div>
            <span className="visual-coordinate">19.0760° N&nbsp; 72.8777° E</span>
          </div>
        </section>

        <section className="opportunities-section" id="opportunities" aria-labelledby="opportunities-title">
          <div className="section-heading">
            <div>
              <div className="eyebrow section-eyebrow">MADE FOR THE CURIOUS</div>
              <h2 id="opportunities-title">Find your next <span>yes.</span></h2>
            </div>
            <div className="results-note"><span className={`live-dot${error ? " offline" : ""}`} /> {error ? "Service unavailable" : loading ? "Finding opportunities" : `${events.length} opportunities`} <span>{error ? "check backend settings" : "across Maharashtra"}</span></div>
          </div>

          <div className="search-row">
            <label className="search-box">
              <Search size={18} aria-hidden="true" />
              <input
                data-testid="event-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Try robotics, debate, football..."
                aria-label="Search opportunities"
              />
              <kbd>↵</kbd>
            </label>
            <label className="select-box">
              <MapPin size={17} aria-hidden="true" />
              <select data-testid="location-filter" value={location} onChange={(event) => setLocation(event.target.value)} aria-label="Filter by city">
                {CITIES.map((city) => <option key={city} value={city}>{city}</option>)}
              </select>
              <ChevronDown size={15} aria-hidden="true" />
            </label>
            <label className="free-toggle" data-testid="free-filter">
              <input type="checkbox" checked={freeOnly} onChange={(event) => setFreeOnly(event.target.checked)} />
              <span className="toggle-track"><span /></span>
              <span>Free to join</span>
            </label>
          </div>

          <div className="filter-toolbar">
            <div className="category-list" role="group" aria-label="Filter by category">
              {CATEGORIES.map((item) => (
                <button
                  className={`category-chip${category === item ? " selected" : ""}`}
                  data-testid={`category-${item.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")}`}
                  key={item}
                  onClick={() => setCategory(item)}
                  type="button"
                >
                  {category === item && <Check size={13} />}{item}
                </button>
              ))}
            </div>
            <div className="mode-control" aria-label="Event format">
              <SlidersHorizontal size={15} aria-hidden="true" />
              {["All", "Physical", "Virtual"].map((item) => (
                <button
                  aria-pressed={mode === item}
                  className={mode === item ? "mode-active" : ""}
                  data-testid={`mode-${item.toLowerCase()}`}
                  key={item}
                  onClick={() => setMode(item)}
                  type="button"
                >{item}</button>
              ))}
            </div>
          </div>

          {error ? (
            <div className="state-panel error-panel" role="alert">
              <div className="state-mark"><Compass size={20} /></div>
              <h3>The opportunity board is offline.</h3>
              <p>{error}</p>
              <button className="text-button" onClick={() => setRefreshKey((key) => key + 1)} type="button">Try again <RotateCw size={14} /></button>
            </div>
          ) : loading ? (
            <div className="loading-grid" aria-label="Loading opportunities">
              {[0, 1, 2].map((item) => <div className="loading-card" key={item}><div /><span /><span /></div>)}
            </div>
          ) : events.length ? (
            <div className="event-grid">
              {events.map((event, index) => (
                <article className={`event-card${index === 0 ? " event-card-featured" : ""}`} key={event.id || event.name}>
                  <div className="event-image-wrap">
                    <img className="event-image" src={imageFor(event)} alt="" loading="lazy" />
                    <span className="event-category">{event.category || "Opportunity"}</span>
                    <span className={`event-mode ${event.mode === "Virtual" ? "virtual" : "physical"}`}>
                      {event.mode === "Virtual" ? <Video size={12} /> : <MapPin size={12} />}
                      {event.mode || "In person"}
                    </span>
                  </div>
                  <div className="event-content">
                    <div className="event-meta"><span><CalendarDays size={14} /> {formatDate(event.date)}</span><span className="meta-divider" /> <span>{event.location || "Maharashtra"}</span></div>
                    <h3>{event.name}</h3>
                    <p className="event-organiser">{event.organiser || event.subcategory || "Open opportunity"}</p>
                    <div className="event-footer">
                      <span className="event-fee">{Number(event.fee) > 0 ? `₹${event.fee}` : "Free"}<small>{Number(event.fee) > 0 ? " entry fee" : " to join"}</small></span>
                      <button className="card-action" data-testid={`event-details-${event.id || index}`} onClick={() => setSelectedEvent(event)} type="button" aria-label={`View ${event.name}`}>
                        <ArrowUpRight size={18} />
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="state-panel">
              <div className="state-mark"><Search size={20} /></div>
              <h3>No matches this time.</h3>
              <p>Try another search or open up your filters. There’s always something worth a look.</p>
              <button className="text-button" onClick={resetFilters} type="button">Clear filters <X size={15} /></button>
            </div>
          )}
        </section>

        <section className="closing-band" id="how-it-works">
          <div className="closing-icon"><Users size={19} /></div>
          <div><span className="eyebrow">YOUR MOVE</span><h2>There’s more to learn by doing.</h2></div>
          <p>From your first quiz to your next big idea, make room for the things you haven’t tried yet.</p>
          <a href="#opportunities" aria-label="Back to opportunities"><ArrowUpRight size={19} /></a>
        </section>
      </main>

      <footer className="site-footer"><a className="footer-brand" href="#top">EVENZA<span>.</span></a><span>Where opportunities find you.</span><span>Made for Maharashtra <span className="footer-star">✳</span></span></footer>

      {selectedEvent && (
        <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedEvent(null); }}>
          <section aria-labelledby="modal-title" aria-modal="true" className="event-modal" role="dialog">
            <button className="modal-close" data-testid="close-event-details" onClick={() => setSelectedEvent(null)} type="button" aria-label="Close event details"><X size={19} /></button>
            <img src={imageFor(selectedEvent)} alt="" />
            <div className="modal-body">
              <span className="eyebrow">{selectedEvent.category || "OPPORTUNITY"}</span>
              <h2 id="modal-title">{selectedEvent.name}</h2>
              <p>{selectedEvent.description || "A new opportunity to learn, meet people, and put your ideas into action."}</p>
              <div className="modal-facts">
                <span><CalendarDays size={16} />{formatDate(selectedEvent.date)}</span>
                <span><MapPin size={16} />{selectedEvent.location || "Maharashtra"}</span>
                <span>{selectedEvent.mode === "Virtual" ? <Video size={16} /> : <Clock3 size={16} />}{selectedEvent.mode || "In person"}</span>
              </div>
              {selectedEvent.eligibility && <div className="eligibility-note"><Sparkles size={15} /> {selectedEvent.eligibility}</div>}
              <div className="modal-bottom"><span className="event-fee">{Number(selectedEvent.fee) > 0 ? `₹${selectedEvent.fee}` : "Free"}<small>{Number(selectedEvent.fee) > 0 ? " entry fee" : " to join"}</small></span><span className="modal-organiser">Hosted by {selectedEvent.organiser || "the organiser"}</span></div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;