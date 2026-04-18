export type AgentType = "academic" | "career" | "social"

export const user = {
  name: "Alex Müller",
  program: "Informatics, B.Sc.",
  semester: "4th semester",
  email: "alex.mueller@tum.de",
  initials: "AM",
}

export const courses = [
  {
    code: "IN0007",
    name: "Fundamentals of Algorithms and Data Structures",
    chair: "Chair of Algorithms and Complexity",
    mastery: 72,
    newSlides: true,
    credits: 8,
    professor: "Prof. Dr. Helmut Seidl",
    lectures: [
      { id: 1, title: "Introduction & Asymptotic Notation", reviewed: true, summary: "Big-O, Omega, Theta notation. Examples with nested loops and recursion." },
      { id: 2, title: "Sorting Algorithms", reviewed: true, summary: "Merge sort, quicksort, heapsort. Average and worst-case analysis." },
      { id: 3, title: "Hash Tables & Collision Resolution", reviewed: false, summary: "Chaining vs open addressing. Load factor and resizing strategies." },
      { id: 4, title: "Graph Algorithms I — BFS/DFS", reviewed: false, summary: "Traversal, connected components, topological sort." },
    ],
  },
  {
    code: "IN2064",
    name: "Machine Learning",
    chair: "Chair of Data Science",
    mastery: 58,
    newSlides: true,
    credits: 6,
    professor: "Prof. Dr. Stephan Günnemann",
    lectures: [
      { id: 1, title: "Linear Regression & Regularization", reviewed: true, summary: "OLS, ridge, lasso. Bias-variance decomposition." },
      { id: 2, title: "Classification & Logistic Regression", reviewed: true, summary: "Sigmoid, cross-entropy, decision boundaries." },
      { id: 3, title: "Neural Networks & Backpropagation", reviewed: false, summary: "Forward/backward pass, chain rule, gradient descent variants." },
      { id: 4, title: "Regularization & Dropout", reviewed: false, summary: "L1/L2, early stopping, dropout theory." },
    ],
  },
  {
    code: "MA0901",
    name: "Linear Algebra for Informatics",
    chair: "Chair of Applied Mathematics",
    mastery: 84,
    newSlides: false,
    credits: 6,
    professor: "Prof. Dr. Barbara Wohlmuth",
    lectures: [
      { id: 1, title: "Vector Spaces", reviewed: true, summary: "Axioms, subspaces, linear independence." },
      { id: 2, title: "Linear Maps & Matrices", reviewed: true, summary: "Representation, kernel, image, rank." },
      { id: 3, title: "Eigenvalues & Diagonalization", reviewed: true, summary: "Characteristic polynomial, eigenspaces." },
    ],
  },
  {
    code: "IN2086",
    name: "Distributed Systems",
    chair: "Chair of Decentralized Systems",
    mastery: 41,
    newSlides: true,
    credits: 6,
    professor: "Prof. Dr. Pramod Bhatotia",
    lectures: [
      { id: 1, title: "Models & Failure Modes", reviewed: true, summary: "Synchronous vs asynchronous, Byzantine failures." },
      { id: 2, title: "Consensus & Raft", reviewed: false, summary: "Leader election, log replication, safety." },
      { id: 3, title: "CRDTs", reviewed: false, summary: "State-based vs op-based, convergence guarantees." },
    ],
  },
  {
    code: "IN2339",
    name: "Introduction to Computer Vision",
    chair: "Chair of Computer Vision",
    mastery: 65,
    newSlides: false,
    credits: 5,
    professor: "Prof. Dr. Daniel Cremers",
    lectures: [
      { id: 1, title: "Image Formation", reviewed: true, summary: "Pinhole camera model, projection matrices." },
      { id: 2, title: "Feature Detection", reviewed: true, summary: "Harris corners, SIFT descriptors." },
    ],
  },
]

export const deadlines = [
  { id: 1, course: "IN2064", task: "Assignment 3: Backpropagation", due: "2026-04-22", weight: "15%", masteryGap: 42, priority: 92 },
  { id: 2, course: "IN0007", task: "Tutorial Sheet 6", due: "2026-04-21", weight: "5%", masteryGap: 28, priority: 78 },
  { id: 3, course: "IN2086", task: "Midterm Exam", due: "2026-04-28", weight: "30%", masteryGap: 59, priority: 88 },
  { id: 4, course: "MA0901", task: "Problem Set 4", due: "2026-04-25", weight: "10%", masteryGap: 16, priority: 54 },
  { id: 5, course: "IN2339", task: "Lab Report: Stereo Vision", due: "2026-05-02", weight: "20%", masteryGap: 35, priority: 71 },
]

export const todayEvents = [
  { id: 1, time: "09:00 – 10:30", title: "IN2064 Lecture: Neural Networks", location: "MI HS 1", agent: "academic" as AgentType },
  { id: 2, time: "13:00 – 14:00", title: "Coffee chat — Celonis recruiter", location: "Stammgelände, Café Jasmin", agent: "career" as AgentType },
  { id: 3, time: "18:00 – 19:30", title: "ZHS Climbing — Boulderwelt", location: "Garching Campus", agent: "social" as AgentType },
]

export const agentActivity = [
  { id: 1, icon: "📚", text: "Summarized new slides from IN0007 (Hash Tables)", time: "12 min ago", agent: "academic" as AgentType },
  { id: 2, icon: "🏋️", text: "ZHS Climbing slot secured for Tue 18:00", time: "1 hour ago", agent: "social" as AgentType },
  { id: 3, icon: "📧", text: "Draft email to Prof. Schmidt ready for review", time: "2 hours ago", agent: "career" as AgentType },
  { id: 4, icon: "📝", text: "Generated 14 flashcards for IN2064 — Backpropagation", time: "3 hours ago", agent: "academic" as AgentType },
  { id: 5, icon: "🍽️", text: "Found 3 overlapping lunch slots with Jonas & Lena", time: "4 hours ago", agent: "social" as AgentType },
  { id: 6, icon: "💼", text: "Matched 2 new working-student roles at BMW & Siemens", time: "yesterday", agent: "career" as AgentType },
]

export const theses = [
  {
    id: 1,
    professor: "Prof. Dr. Stephan Günnemann",
    chair: "Chair of Data Science",
    topic: "Robust Graph Neural Networks under Distribution Shift",
    matchScore: 94,
    reasoning: "Matches your ML (IN2064) + Distributed Systems (IN2086) background, strong fit for graph-based work.",
    tags: ["GNN", "ML", "Research"],
  },
  {
    id: 2,
    professor: "Prof. Dr. Daniel Cremers",
    chair: "Chair of Computer Vision",
    topic: "Self-Supervised Depth Estimation from Monocular Video",
    matchScore: 87,
    reasoning: "Aligns with your IN2339 Computer Vision grade (1.7) and your Python/PyTorch proficiency.",
    tags: ["CV", "Self-Supervised"],
  },
  {
    id: 3,
    professor: "Prof. Dr. Pramod Bhatotia",
    chair: "Chair of Decentralized Systems",
    topic: "Verifiable Compute for Serverless Edge Functions",
    matchScore: 81,
    reasoning: "Distributed Systems coursework and your Rust side project make you a plausible fit.",
    tags: ["Systems", "Security"],
  },
  {
    id: 4,
    professor: "Prof. Dr. Björn Menze",
    chair: "Chair of Biomedical Image Analysis",
    topic: "Federated Learning for Multi-Hospital Segmentation",
    matchScore: 76,
    reasoning: "Combines ML + Distributed Systems, but limited overlap with biomedical domain knowledge.",
    tags: ["Federated", "Medical"],
  },
]

export const studyRooms = [
  { id: 1, name: "MI 02.07.023", building: "Mathematik-Informatik", capacity: 4, amenities: ["Whiteboard", "Monitor", "Quiet zone"], availableUntil: "17:00" },
  { id: 2, name: "MI 00.09.022", building: "Mathematik-Informatik", capacity: 8, amenities: ["Projector", "Whiteboard"], availableUntil: "18:30" },
  { id: 3, name: "Stammgelände N1105", building: "Stammgelände", capacity: 6, amenities: ["Whiteboard", "Power"], availableUntil: "16:30" },
  { id: 4, name: "Garching FMI 01.03", building: "Garching Campus", capacity: 2, amenities: ["Silent study"], availableUntil: "19:00" },
]

export const profile = {
  headline: "CS undergrad focused on ML systems and distributed computing",
  summary:
    "4th-semester Informatics student at TUM with strong foundations in algorithms, machine learning, and distributed systems. Comfortable shipping TypeScript and Python; interested in ML infrastructure and applied research.",
  skills: [
    { name: "Python", level: 90, source: "IN2064, personal projects" },
    { name: "TypeScript", level: 78, source: "Web dev side projects" },
    { name: "Machine Learning", level: 72, source: "IN2064 (1.3)" },
    { name: "Distributed Systems", level: 55, source: "IN2086 (in progress)" },
    { name: "Linear Algebra", level: 85, source: "MA0901 (1.0)" },
    { name: "Rust", level: 40, source: "Self-taught" },
  ],
  projects: [
    { name: "tum-flashcards", desc: "OSS Anki exporter for TUM slide decks", stars: 142 },
    { name: "raft-visualizer", desc: "Interactive Raft consensus demo", stars: 58 },
  ],
}

export const cvFlags = [
  { level: "critical" as const, text: "Email 'gamer_king99@gmail.com' is unprofessional — use your TUM address." },
  { level: "critical" as const, text: "Missing: IN2064 Machine Learning (grade 1.3). Highly relevant to listed roles." },
  { level: "warning" as const, text: "Tech stack outdated: consider adding TypeScript and PyTorch." },
  { level: "warning" as const, text: "Project 'Tetris Clone' lacks impact metrics — add users or performance numbers." },
  { level: "good" as const, text: "Clear section hierarchy and consistent date formatting." },
  { level: "good" as const, text: "Strong GPA (1.4) prominently featured in education block." },
]

export const jobs = [
  {
    id: 1,
    company: "BMW Group",
    title: "Working Student — ML Infrastructure",
    location: "Munich, Germany",
    type: "working-student" as const,
    matchScore: 91,
    reasoning: "Your Python + ML + Distributed Systems coursework aligns tightly with this role's stack.",
    salary: "€20/h",
    posted: "2 days ago",
  },
  {
    id: 2,
    company: "Celonis",
    title: "Working Student — Platform Engineering",
    location: "Munich, Germany",
    type: "working-student" as const,
    matchScore: 84,
    reasoning: "TypeScript and systems background fit. Missing Kubernetes experience.",
    salary: "€22/h",
    posted: "5 days ago",
  },
  {
    id: 3,
    company: "Siemens",
    title: "Internship — Industrial AI",
    location: "Munich, Germany",
    type: "internship" as const,
    matchScore: 79,
    reasoning: "ML coursework is a strong match; domain exposure to industrial applications would help.",
    salary: "€1,800/mo",
    posted: "1 week ago",
  },
  {
    id: 4,
    company: "Personio",
    title: "Working Student — Frontend",
    location: "Munich, Germany",
    type: "working-student" as const,
    matchScore: 72,
    reasoning: "Your TypeScript + React side projects map well; less direct coursework support.",
    salary: "€21/h",
    posted: "3 days ago",
  },
  {
    id: 5,
    company: "BMW Group",
    title: "New Grad — Software Engineer (Autonomous Driving)",
    location: "Munich, Germany",
    type: "new-grad" as const,
    matchScore: 68,
    reasoning: "Requires C++ experience you haven't demonstrated yet. Strong ML match otherwise.",
    salary: "€62,000/y",
    posted: "1 week ago",
  },
]

export const careerEvents = [
  { id: 1, title: "Munich AI Engineers Meetup", source: "Luma", date: "Apr 24", topic: "LLM infra & evals", fitScore: 89, location: "Werksviertel" },
  { id: 2, title: "Celonis Process Mining Workshop", source: "Reply", date: "Apr 27", topic: "Data pipelines", fitScore: 76, location: "Celonis HQ" },
  { id: 3, title: "TUM AI Lecture Series — Günnemann", source: "Luma", date: "May 3", topic: "Graph ML", fitScore: 94, location: "MI HS 2" },
  { id: 4, title: "BMW Tech Day — Autonomous Driving", source: "Luma", date: "May 8", topic: "CV & planning", fitScore: 71, location: "BMW Welt" },
]

export const zhsTrackers = [
  { id: 1, sport: "Climbing", venue: "Boulderwelt Ost", opensIn: "2h 14m", priority: "high" as const, status: "watching" as const, preferred: "Tue/Thu 18:00" },
  { id: 2, sport: "Bouldering", venue: "Einstein Boulderhalle", opensIn: "14h 03m", priority: "medium" as const, status: "booked" as const, preferred: "Wed 19:00" },
  { id: 3, sport: "Badminton", venue: "ZHS Hall 2", opensIn: "3d 12h", priority: "medium" as const, status: "watching" as const, preferred: "Fri 16:00" },
  { id: 4, sport: "Swimming", venue: "Olympiabad", opensIn: "—", priority: "low" as const, status: "missed" as const, preferred: "Mon 07:00" },
]

export const socialEvents = [
  { id: 1, title: "ESN Welcome Drinks", date: "Apr 22", time: "19:00", location: "Löwenbräukeller", category: "Social", free: true },
  { id: 2, title: "TUMi Alpine Hike — Tegernsee", date: "Apr 26", time: "08:00", location: "Meet at HBF", category: "Outdoor", free: false },
  { id: 3, title: "ESN International Dinner", date: "Apr 29", time: "19:30", location: "Stammgelände Mensa", category: "Food", free: true },
  { id: 4, title: "TUMi Language Café", date: "May 2", time: "18:00", location: "Olympia Park", category: "Social", free: true },
  { id: 5, title: "ESN Oktoberfest-Style Pub Crawl", date: "May 5", time: "20:00", location: "Altstadt", category: "Nightlife", free: false },
  { id: 6, title: "TUMi Lake Day — Starnberger See", date: "May 9", time: "10:00", location: "S6 to Starnberg", category: "Outdoor", free: false },
]

export const friends = [
  { id: 1, name: "Jonas Weber", initials: "JW" },
  { id: 2, name: "Lena Schmidt", initials: "LS" },
  { id: 3, name: "Tobias Becker", initials: "TB" },
  { id: 4, name: "Marie Fischer", initials: "MF" },
]

export const mensaMenu = [
  { id: 1, name: "Schweinebraten mit Knödel", price: "€4.20", tags: ["meat"] },
  { id: 2, name: "Pasta Pesto mit Parmesan", price: "€3.50", tags: ["vegetarian"] },
  { id: 3, name: "Veganer Linseneintopf", price: "€2.90", tags: ["vegan"] },
  { id: 4, name: "Kaiserschmarrn mit Apfelmus", price: "€3.80", tags: ["vegetarian", "dessert"] },
  { id: 5, name: "Gebackener Seelachs mit Kartoffelsalat", price: "€4.60", tags: ["fish"] },
]

export const calendarEvents = [
  { id: 1, day: 0, start: 9, end: 10.5, title: "IN2064 Lecture", agent: "academic" as AgentType, location: "MI HS 1" },
  { id: 2, day: 0, start: 13, end: 14, title: "Celonis coffee chat", agent: "career" as AgentType, location: "Café Jasmin" },
  { id: 3, day: 0, start: 18, end: 19.5, title: "ZHS Climbing", agent: "social" as AgentType, location: "Garching" },
  { id: 4, day: 1, start: 10, end: 11.5, title: "IN0007 Tutorial", agent: "academic" as AgentType, location: "MI 00.08.038" },
  { id: 5, day: 1, start: 14, end: 16, title: "Study block: IN2086", agent: "academic" as AgentType, location: "MI Library", conflict: true },
  { id: 6, day: 1, start: 15, end: 16, title: "ESN Welcome Drinks RSVP", agent: "social" as AgentType, location: "Löwenbräukeller", conflict: true },
  { id: 7, day: 2, start: 9, end: 10.5, title: "IN2086 Lecture", agent: "academic" as AgentType, location: "MI HS 2" },
  { id: 8, day: 2, start: 12, end: 13, title: "Lunch w/ Jonas & Lena", agent: "social" as AgentType, location: "Mensa Garching" },
  { id: 9, day: 2, start: 16, end: 17, title: "BMW recruiter call", agent: "career" as AgentType, location: "Zoom" },
  { id: 10, day: 3, start: 11, end: 12.5, title: "MA0901 Lecture", agent: "academic" as AgentType, location: "MI HS 1" },
  { id: 11, day: 3, start: 14, end: 15.5, title: "Thesis outreach — Prof. Günnemann", agent: "career" as AgentType, location: "Email" },
  { id: 12, day: 4, start: 10, end: 12, title: "IN2339 Lab", agent: "academic" as AgentType, location: "MI 02.05.037" },
  { id: 13, day: 4, start: 17, end: 19, title: "ZHS Badminton", agent: "social" as AgentType, location: "ZHS Hall 2" },
  { id: 14, day: 5, start: 10, end: 12, title: "Study block: Midterm prep", agent: "academic" as AgentType, location: "MI Library" },
  { id: 15, day: 6, start: 14, end: 17, title: "TUMi Alpine Hike", agent: "social" as AgentType, location: "Tegernsee" },
]

export const weekDays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

export const agentLabel: Record<AgentType, string> = {
  academic: "Academic",
  career: "Career",
  social: "Social",
}
