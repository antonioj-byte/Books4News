"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function IrAlUltimoDia() {
  const router = useRouter();
  const [error, setError] = useState("");
  useEffect(() => {
    api.dias()
      .then((dias) => (dias.length ? router.replace(`/dia/${dias[0].fecha}`) : setError("Aún no hay ejecuciones. Lanza `uv run folio run`.")))
      .catch(() => setError("No responde la API. Arráncala con `uv run folio web`."));
  }, [router]);
  return <p className="p-6 text-tinta-suave">{error || "Cargando el último día…"}</p>;
}
