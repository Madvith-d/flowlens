import { redirect } from "next/navigation";

/** `/` always routes into the authenticated area; guards handle sign-in. */
export default function Home() {
  redirect("/dashboard");
}
