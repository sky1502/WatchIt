import { getApp, getApps, initializeApp } from "firebase/app";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

if (!firebaseConfig.apiKey) {
  throw new Error("Missing Firebase configuration. Set NEXT_PUBLIC_FIREBASE_* env vars.");
}

const app = getApps().length ? getApp() : initializeApp(firebaseConfig);

export default app;
