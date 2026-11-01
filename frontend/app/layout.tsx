import type { Metadata } from 'next';
import './style.css';
export const metadata: Metadata = {title:'PeakGuard AI | Capacity intelligence',description:'Simulações sintéticas de capacidade e custos.'};
export default function Layout({children}:{children:React.ReactNode}) {return <html lang="pt-BR"><body>{children}</body></html>}
