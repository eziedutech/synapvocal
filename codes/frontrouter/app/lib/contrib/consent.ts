// The consent text people agree to. Its date is its version, and backpy only accepts
// consent for the version it knows (CONSENT_VERSION in codes/backpy/app/contrib/api.py).
// Any change to the wording needs a new date in both places.
export const CONSENT_VERSION = "2026-09-18";

export const CONTROLLER = "EZI Edutech Dev";
export const CONTACT_EMAIL = "zia@eziedutech.dev";

export const CONSENT_SECTIONS: { title: string; points: string[] }[] = [
  {
    title: "Why we ask",
    points: [
      "Speech recognition is trained mostly on typical voices, which is why it often mishears people with dysarthria and people speaking with Parkinson's disease, ALS, cerebral palsy, Down syndrome or after a stroke.",
      "Recordings paired with the sentence the speaker confirmed are the most useful data there is for making it hear these voices better. Very little of it exists.",
    ],
  },
  {
    title: "What is saved, and only when you choose",
    points: [
      "Nothing is saved automatically. After you confirm a sentence on the Bridge, you decide whether to contribute that one sentence.",
      "For each sentence you contribute: the recording of that sentence, what speech recognition heard, the sentence you confirmed, whether you said it is exactly what you said, and which models were used.",
      "From your Google account: your name, email address and account id, so your contributions can be shown to you and deleted on request.",
    ],
  },
  {
    title: "How it is used",
    points: [
      `${CONTROLLER} uses the recordings to train and test speech recognition models for people whose speech is hard to understand.`,
      "Recordings are never sold, never published and never shared with other organisations. Models trained on them may be published; the recordings themselves are not.",
      "Your voice and the fact that you use this service can reveal a health condition. That is why this is voluntary and why you can undo it at any time.",
    ],
  },
  {
    title: "Where it is kept",
    points: [
      "Recordings are stored encrypted in private cloud storage. Account details and sentence texts are stored in a database on our own server.",
      "Recordings are filed under random ids, never under your name or email.",
      "They are kept until you delete them or your account.",
    ],
  },
  {
    title: "Your choices",
    points: [
      "Contributing is voluntary. The Bridge works exactly the same if you never sign in.",
      "You can see your contributions, delete any of them, withdraw your consent, or delete your account and everything with it, at any time on this page.",
      `Questions or requests: ${CONTACT_EMAIL}.`,
    ],
  },
];
